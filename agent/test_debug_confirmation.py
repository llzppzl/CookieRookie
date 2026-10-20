"""agent/test_debug_confirmation.py - debug mode asks before edits and commands"""
import builtins

from agent.core import DebugAgent, approve_all, ask_in_terminal, preview_action


class ScriptedLLM:
    """Returns scripted replies in order and records the context of each call"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(context)
        return self.replies.pop(0)


def edit(path, line, new_string):
    return {"thought": "fix it", "done": False,
            "action": {"tool": "edit_file", "args": {"path": path, "line": line, "new_string": new_string}}}


DONE = {"thought": "done", "done": True, "summary": "finished", "action": {}}


def make_file(tmp_path):
    f = tmp_path / "app.py"
    f.write_text("x = 1\n", encoding="utf-8")
    return f


def test_declined_edit_does_not_run_and_model_is_told(tmp_path):
    f = make_file(tmp_path)
    llm = ScriptedLLM([edit(str(f), 1, "x = 10"), DONE])
    agent = DebugAgent(llm, ask=lambda tool, args: ("no", "use 2 instead"))

    assert agent.run("bug") == "finished"
    assert f.read_text(encoding="utf-8") == "x = 1\n"
    result = llm.contexts[-1]["history"][-1]["result"]
    assert result["success"] is False
    assert "use 2 instead" in result["error"]


def test_allowed_edit_runs(tmp_path):
    f = make_file(tmp_path)
    llm = ScriptedLLM([edit(str(f), 1, "x = 10"), DONE])
    agent = DebugAgent(llm, ask=lambda tool, args: ("yes", ""))

    agent.run("bug")
    assert f.read_text(encoding="utf-8") == "x = 10\n"


def test_all_stops_asking(tmp_path):
    f = make_file(tmp_path)
    asked = []

    def ask(tool, args):
        asked.append(tool)
        return "all", ""

    llm = ScriptedLLM([edit(str(f), 1, "x = 2"), edit(str(f), 1, "x = 3"), DONE])
    DebugAgent(llm, ask=ask).run("bug")
    assert asked == ["edit_file"]
    assert f.read_text(encoding="utf-8") == "x = 3\n"


def test_quit_stops_before_the_change(tmp_path):
    f = make_file(tmp_path)
    llm = ScriptedLLM([edit(str(f), 1, "x = 10"), DONE])
    result = DebugAgent(llm, ask=lambda tool, args: ("quit", "")).run("bug")

    assert result.startswith("Stopped before edit_file")
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_safe_tools_are_not_asked(tmp_path):
    f = make_file(tmp_path)
    read = {"thought": "look", "done": False, "action": {"tool": "read_file", "args": {"path": str(f)}}}

    def ask(tool, args):
        raise AssertionError("read_file should not ask")

    llm = ScriptedLLM([read, DONE])
    assert DebugAgent(llm, ask=ask).run("bug") == "finished"


def test_tool_error_goes_back_to_model(tmp_path):
    bad = {"thought": "read", "done": False,
           "action": {"tool": "read_file", "args": {"path": "x", "made_up": 1}}}
    llm = ScriptedLLM([bad, DONE])

    assert DebugAgent(llm, ask=approve_all).run("bug") == "finished"
    result = llm.contexts[-1]["history"][-1]["result"]
    assert result["success"] is False
    assert "TypeError" in result["error"]


def test_no_terminal_means_quit(monkeypatch):
    def no_input(prompt=""):
        raise EOFError

    monkeypatch.setattr(builtins, "input", no_input)
    answer, reason = ask_in_terminal("exec", {"command": "rm -rf build"})
    assert answer == "quit"
    assert "--yes" in reason


def test_typed_text_declines_and_is_passed_on(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "only touch tests/")
    assert ask_in_terminal("exec", {"command": "ls"}) == ("no", "only touch tests/")


def test_preview_shows_old_and_new_line(tmp_path):
    f = make_file(tmp_path)
    text = preview_action("edit_file", {"path": str(f), "line": 1, "new_string": "x = 10"})
    assert "- x = 1" in text
    assert "+ x = 10" in text
    assert "rm -rf build" in preview_action("exec", {"command": "rm -rf build"})
