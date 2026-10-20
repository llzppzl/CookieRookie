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
