"""A tool name the model made up is reported back to it instead of ending the task."""
from unittest.mock import MagicMock

from agent import tools
from agent.core import DebugAgent, InteractiveAgent
from agent.tool_system import tool_system

UNKNOWN = {"thought": "list the folder", "action": {"tool": "list_dir", "args": {"path": "."}}, "done": False}
READ = {"thought": "read it", "action": {"tool": "read_file", "args": {"path": "missing.py"}}, "done": False}
DONE = {"thought": "ok", "action": {}, "done": True, "summary": "finished"}


def make_llm(*replies):
    """A fake LLM that answers with replies in order and keeps a copy of the history of each call
    (the agent keeps appending to the same context dict)."""
    llm = MagicMock()
    llm.histories = []
    answers = iter(replies)

    def chat(context):
        llm.histories.append(list(context["history"]))
        return dict(next(answers))

    llm.chat.side_effect = chat
    return llm


def history_sent_on(llm, call):
    return llm.histories[call]


def check_reported(llm):
    entry = history_sent_on(llm, 1)[-1]
    assert entry["action"]["tool"] == "list_dir"
    assert entry["result"]["success"] is False
    assert "Unknown tool 'list_dir'" in entry["result"]["error"]
    assert "read_file" in entry["result"]["error"]  # it learns which tools exist


def test_debug_agent_reports_unknown_tool_and_goes_on():
    llm = make_llm(UNKNOWN, DONE)
    assert DebugAgent(llm).run("bug") == "finished"
    assert llm.chat.call_count == 2
    check_reported(llm)


def test_interactive_agent_reports_unknown_tool_and_goes_on():
    tools.register_base_tools()
    llm = make_llm(UNKNOWN, DONE)
    assert InteractiveAgent(llm, tool_system).run("task") == "finished"
    assert llm.chat.call_count == 2
    check_reported(llm)


def test_interactive_agent_after_confirm_reports_unknown_tool():
    tools.register_base_tools()
    llm = make_llm(UNKNOWN, READ, DONE)
    agent = InteractiveAgent(llm, tool_system)
    context = {"task": "task", "history": [], "system": ""}
    assert agent.run_from_context(context) == "finished"
    check_reported(llm)
    # the next tool call runs normally
    assert history_sent_on(llm, 2)[-1]["action"]["tool"] == "read_file"
