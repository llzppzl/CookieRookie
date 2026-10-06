"""cookierookie/test_confirmation.py - asking before edits and commands, and errors that don't end the session (fake LLM, no API calls)"""
import copy

import pytest
import requests

from cookierookie import cli
from cookierookie.core import (DebugAgent, InteractiveAgent, approve_all, ask_in_terminal,
                               coerce_args, preview_action)
from cookierookie.tool_system import tool_system
import cookierookie.tools as tools_module


class ScriptedLLM:
    """Returns the given replies in order and records the context of each call"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(copy.deepcopy(context))
        return self.responses.pop(0)


def setup_module(module):
    tools_module.register_base_tools()


def edit(path, line, new_string):
    return {"thought": "fix it", "action": {"tool": "edit_file", "args": {"path": str(path), "line": line, "new_string": new_string}}, "done": False}


def finish(summary="done"):
    return {"thought": "finished", "action": {}, "done": True, "summary": summary}


class Answers:
    """Stands in for the user at the y/N/a/q prompt"""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def __call__(self, tool_name, args):
        self.asked.append(tool_name)
        return self.answers.pop(0)


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("x = 1\ny = 2\n")
    return path


# ---------- debug mode ----------

def test_debug_mode_asks_before_an_edit_and_respects_no(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10"), finish("left it alone")])
    ask = Answers(("no", "x is fine, look at y"))

    result = DebugAgent(llm, ask=ask).run("x is wrong")

    assert ask.asked == ["edit_file"]
    assert app.read_text() == "x = 1\ny = 2\n"
    told = llm.contexts[-1]["history"][-1]["result"]
    assert told["success"] is False
    assert "x is fine, look at y" in told["error"]
    assert result == "left it alone"


def test_debug_mode_runs_the_edit_after_yes(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10"), finish()])

    DebugAgent(llm, ask=Answers(("yes", ""))).run("x is wrong")

    assert app.read_text() == "x = 10\ny = 2\n"


def test_reading_does_not_ask(app):
    llm = ScriptedLLM([
        {"thought": "look", "action": {"tool": "read_file", "args": {"path": str(app)}}, "done": False},
        finish(),
    ])
    ask = Answers()

    DebugAgent(llm, ask=ask).run("x is wrong")

    assert ask.asked == []


def test_all_stops_asking_for_the_rest_of_the_run(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10"), edit(app, 2, "y = 20"), finish()])
    ask = Answers(("all", ""))

    DebugAgent(llm, ask=ask).run("x and y are wrong")

    assert ask.asked == ["edit_file"]
    assert app.read_text() == "x = 10\ny = 20\n"


def test_quit_stops_before_running_anything(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10")])

    result = DebugAgent(llm, ask=Answers(("quit", ""))).run("x is wrong")

    assert result.startswith("Stopped before edit_file")
    assert app.read_text() == "x = 1\ny = 2\n"


def test_yes_flag_runs_everything_without_asking(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10"), finish()])

    DebugAgent(llm, ask=approve_all).run("x is wrong")

    assert app.read_text() == "x = 10\ny = 2\n"


# ---------- the prompt ----------

@pytest.mark.parametrize("typed, expected", [
    ("y", ("yes", "")),
    ("YES", ("yes", "")),
    ("a", ("all", "")),
    ("q", ("quit", "")),
    ("", ("no", "")),
    ("n", ("no", "")),
    ("use the logger instead", ("no", "use the logger instead")),
])
def test_prompt_answers(monkeypatch, typed, expected):
    monkeypatch.setattr("builtins.input", lambda prompt: typed)
    assert ask_in_terminal("exec", {"command": "ls"}) == expected


def test_prompt_without_a_terminal_stops_and_mentions_yes(monkeypatch):
    def no_terminal(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_terminal)
    answer, reason = ask_in_terminal("exec", {"command": "ls"})

    assert answer == "quit"
    assert "--yes" in reason


def test_preview_shows_the_line_that_changes(app):
    text = preview_action("edit_file", {"path": str(app), "line": 2, "new_string": "y = 20"})
    assert "- y = 2" in text
    assert "+ y = 20" in text


def test_preview_of_write_file_and_exec(app, tmp_path):
    assert preview_action("write_file", {"path": str(app), "content": "a\nb\n"}).startswith(f"Overwrite {app} (2 lines)")
    assert preview_action("write_file", {"path": str(tmp_path / "new.py"), "content": "a\n"}).startswith("Create")
    assert "python -m pytest" in preview_action("exec", {"command": "python -m pytest"})


# ---------- tool errors ----------

def test_a_bad_tool_call_is_reported_to_the_model_not_raised(app):
    llm = ScriptedLLM([
        {"thought": "read", "action": {"tool": "read_file", "args": {"path": str(app), "lines": 5}}, "done": False},
        finish(),
    ])

    assert DebugAgent(llm, ask=approve_all).run("x is wrong") == "done"

    told = llm.contexts[-1]["history"][-1]["result"]
    assert told["success"] is False
    assert "unexpected keyword argument 'lines'" in told["error"]


def test_interactive_mode_survives_a_bad_tool_call(app):
    llm = ScriptedLLM([
        {"thought": "read", "action": {"tool": "find_files", "args": {"glob": "*.py"}}, "done": False},
        finish(),
    ])

    assert InteractiveAgent(llm, tool_system).run("look around") == "done"
    assert "glob" in llm.contexts[-1]["history"][-1]["result"]["error"]


def test_network_error_stops_with_a_clear_message(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(cli.requests, "post", refuse)
    reply = cli.LLMClient("key", base_url="http://localhost:9").chat({"task": "t", "history": [], "system": ""})

    assert reply["fatal"] is True
    assert "Could not reach http://localhost:9" in reply["error"]


# ---------- interactive /edit and /reject ----------

def test_edit_changes_only_the_given_arguments_and_converts_numbers(app):
    llm = ScriptedLLM([edit(app, 1, "y = 20"), finish()])
    agent = InteractiveAgent(llm, tool_system)
    assert agent.run("y is wrong") == "awaiting_confirmation"

    agent.edit_and_confirm({"line": "2"})  # /edit line=2

    assert app.read_text() == "x = 1\ny = 20\n"


def test_edit_with_a_bad_value_runs_nothing_and_keeps_the_action(app):
    agent = InteractiveAgent(ScriptedLLM([edit(app, 1, "x = 10")]), tool_system)
    agent.run("x is wrong")

    assert "line must be a number" in agent.edit_and_confirm({"line": "two"})
    assert "not an argument" in agent.edit_and_confirm({"lines": "2"})
    assert agent.pending_action is not None
    assert app.read_text() == "x = 1\ny = 2\n"


def test_reject_with_a_reason_carries_on_with_the_same_task(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10"), finish("fixed y instead")])
    agent = InteractiveAgent(llm, tool_system)
    agent.run("fix the bug in app.py")

    assert agent.reject("leave x, the bug is in y") == "fixed y instead"

    resumed = llm.contexts[-1]
    assert resumed["task"] == "fix the bug in app.py"
    assert "leave x, the bug is in y" in resumed["history"][-1]["result"]["error"]
    assert app.read_text() == "x = 1\ny = 2\n"


def test_reject_without_a_reason_stops(app):
    llm = ScriptedLLM([edit(app, 1, "x = 10")])
    agent = InteractiveAgent(llm, tool_system)
    agent.run("fix the bug in app.py")

    assert "task stopped" in agent.reject()
    assert len(llm.contexts) == 1


def test_coerce_args_uses_the_tool_signature():
    def tool(path: str, line: int = None, force: bool = False, note=""):
        pass

    assert coerce_args(tool, {"line": "3", "force": "true", "note": "7", "path": "a.py"}) == \
        {"line": 3, "force": True, "note": "7", "path": "a.py"}


# ---------- command line ----------

def test_parse_edit_args_keeps_quoted_values_together():
    assert cli.parse_edit_args(' command="python -m pytest -q" timeout=60') == \
        {"command": "python -m pytest -q", "timeout": "60"}
    with pytest.raises(ValueError):
        cli.parse_edit_args("python")
    with pytest.raises(ValueError):
        cli.parse_edit_args("")


def test_yes_flag_in_any_position(monkeypatch):
    monkeypatch.delenv("DEBUG_BUG_REPORT", raising=False)
    assert cli.parse_args(["--yes", "it crashes"]).yes is True
    assert cli.parse_args(["it crashes", "-y"]).bug == "it crashes"
    assert cli.parse_args([]).bug is None
    with pytest.raises(SystemExit):
        cli.parse_args(["--yes"])  # nothing to debug
