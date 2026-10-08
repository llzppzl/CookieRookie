"""agent/test_edit_command.py - /edit changes only the arguments given, with the tool's types"""
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
import agent.tools as tools_module

tools_module.register_base_tools()

DONE = {"thought": "done", "done": True, "summary": "finished", "action": {}}


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, context):
        return self.replies.pop(0)


def pending_edit(tmp_path):
    f = tmp_path / "app.py"
    f.write_text("x = 1\ny = 2\n", encoding="utf-8")
    agent = InteractiveAgent(ScriptedLLM([DONE]), tool_system)
    args = {"path": str(f), "line": 1, "new_string": "x = 10"}
    agent.pending_action = {"thought": "fix x", "action": {"tool": "edit_file", "args": dict(args)},
                            "tool_name": "edit_file", "tool_args": args}
    return agent, f


def test_edit_keeps_the_arguments_not_given_and_converts_numbers(tmp_path):
    agent, f = pending_edit(tmp_path)

    assert agent.edit_and_confirm({"line": "2", "new_string": "y = 20"}) == "finished"
    assert f.read_text(encoding="utf-8") == "x = 1\ny = 20\n"


def test_unknown_argument_runs_nothing_and_keeps_the_action(tmp_path):
    agent, f = pending_edit(tmp_path)

    result = agent.edit_and_confirm({"lines": "2"})
    assert result.startswith("Nothing ran: 'lines' is not an argument of this tool")
    assert agent.pending_action is not None
    assert f.read_text(encoding="utf-8") == "x = 1\ny = 2\n"


def test_bad_number_runs_nothing(tmp_path):
    agent, f = pending_edit(tmp_path)

    assert "line must be a number" in agent.edit_and_confirm({"line": "two"})
    assert agent.pending_action is not None


def test_booleans_are_converted():
    from agent.tools import find_files
    assert InteractiveAgent._coerce_args(find_files, {"use_regex": "true", "pattern": "x"}) == \
        {"use_regex": True, "pattern": "x"}


def test_cli_keeps_quoted_values_together(monkeypatch, tmp_path):
    """/edit command="pytest -x" reaches the agent as one value"""
    import builtins
    import main

    seen = {}

    class FakeAgent:
        current_plan = None
        pending_action = {"action": {"tool": "exec"}}

        def edit_and_confirm(self, modifications):
            seen.update(modifications)
            self.pending_action = None
            return "ran"

    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k", "model": "m", "base_url": "u", "max_tokens": 1})
    monkeypatch.setattr("agent.core.create_interactive_agent", lambda *a, **k: FakeAgent())
    inputs = iter(['/edit command="pytest -x" timeout=60', "exit"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(inputs))

    main.interactive_main()
    assert seen == {"command": "pytest -x", "timeout": "60"}
