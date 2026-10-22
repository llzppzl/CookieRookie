"""Interactive mode shows what an edit or command will do before /confirm"""

from unittest.mock import MagicMock

from agent.core import InteractiveAgent
from agent.tool_system import ToolSystem


def show(capsys, tool_name, tool_args):
    agent = InteractiveAgent(MagicMock(), ToolSystem())
    agent.pending_action = {"thought": "fix it", "action": {"tool": tool_name, "args": tool_args},
                            "tool_name": tool_name, "tool_args": tool_args}
    agent._show_pending_action()
    return capsys.readouterr().out


def test_edit_by_line_shows_the_old_and_the_new_line(tmp_path, capsys):
    path = tmp_path / "app.py"
    path.write_text("a = 1\nb = 2\n")
    out = show(capsys, "edit_file", {"path": str(path), "line": 2, "new_string": "b = 3"})
    assert f"Edit {path}, line 2:" in out
    assert "- b = 2" in out
    assert "+ b = 3" in out


def test_write_file_shows_the_file_line_by_line(tmp_path, capsys):
    path = tmp_path / "new.py"
    out = show(capsys, "write_file", {"path": str(path), "content": "one\ntwo\n"})
    assert f"Create {path} (2 lines):" in out
    assert "+ one\n+ two" in out


def test_long_files_are_cut_in_the_preview(tmp_path, capsys):
    content = "".join(f"line {i}\n" for i in range(100))
    out = show(capsys, "write_file", {"path": str(tmp_path / "big.py"), "content": content})
    assert "+ line 0" in out
    assert "+ line 99" not in out
    assert "more lines" in out


def test_exec_shows_the_command(capsys):
    out = show(capsys, "exec", {"command": "pytest -x", "workdir": "src"})
    assert "Run command (workdir=src):\n  pytest -x" in out


def test_test_run_shows_the_test_command(tmp_path, capsys):
    (tmp_path / "test_calc.py").write_text("def test_one():\n    assert True\n")
    out = show(capsys, "test_run", {"path": str(tmp_path), "pattern": "test_*.py", "framework": "pytest"})
    assert f"Run the tests (pytest) in {tmp_path}:" in out
    assert "-m pytest -v test_calc.py" in out


def test_test_run_preview_says_when_it_cannot_run(tmp_path, capsys):
    out = show(capsys, "test_run", {"path": str(tmp_path / "missing")})
    assert "this will fail: Directory not found" in out


def test_test_run_waits_for_confirm_and_runs_nothing_before(tmp_path, monkeypatch):
    """Before, test_run ran the project's tests (its code) as soon as the model asked for it"""
    from agent import tools, test_tools
    from agent.tool_system import tool_system

    tools.register_base_tools()
    calls = []
    monkeypatch.setattr(test_tools.subprocess, "run", lambda *a, **k: calls.append(a))
    llm = MagicMock()
    llm.chat.return_value = {"thought": "run them", "action": {"tool": "test_run", "args": {"path": str(tmp_path)}},
                             "done": False, "raw": ""}
    agent = InteractiveAgent(llm, tool_system)
    assert agent.run("run the tests") == "awaiting_confirmation"
    assert agent.pending_action["tool_name"] == "test_run"
    assert calls == []
