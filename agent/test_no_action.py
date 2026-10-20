"""A reply without an action is reported back to the model, and the agent stops after a few in a
row instead of sending the same request until max_iterations runs out."""
from unittest.mock import MagicMock

from agent import tools
from agent.core import DebugAgent, InteractiveAgent, MAX_REPLIES_WITHOUT_ACTION
from agent.tool_system import tool_system

PROSE = {"action": None, "error": "Failed to parse: I will read the file now.", "raw": "I will read the file now."}
READ = {"thought": "read it", "action": {"tool": "read_file", "args": {"path": "missing.py"}}, "done": False}
DONE = {"thought": "ok", "action": {}, "done": True, "summary": "finished"}


def make_llm(*replies):
    """A fake LLM that answers with replies in order (the last one again when they run out) and
    keeps a copy of the history it was sent on each call."""
    llm = MagicMock()
    llm.histories = []
    answers = list(replies)

    def chat(context):
        llm.histories.append(list(context["history"]))
        return dict(answers.pop(0) if len(answers) > 1 else answers[0])

    llm.chat.side_effect = chat
    return llm


def check_told(llm, call=1):
    step = llm.histories[call][-1]
    assert step["result"]["success"] is False
    assert "no action in the reply format" in step["result"]["error"]
    assert "I will read the file now." in step["result"]["error"]  # it sees what it wrote


def interactive():
    tools.register_base_tools()
    return InteractiveAgent


def test_debug_agent_tells_the_model_and_goes_on():
    llm = make_llm(PROSE, DONE)
    assert DebugAgent(llm).run("bug") == "finished"
    check_told(llm)


def test_interactive_agent_tells_the_model_and_goes_on():
    llm = make_llm(PROSE, DONE)
    assert interactive()(llm, tool_system).run("task") == "finished"
    check_told(llm)


def test_interactive_agent_stops_after_replies_without_action():
    llm = make_llm(PROSE)
    result = interactive()(llm, tool_system, max_iterations=50).run("task")
    # Before: 50 identical requests, then "Max iterations reached"
    assert llm.chat.call_count == MAX_REPLIES_WITHOUT_ACTION
    assert result.startswith("Stopped:") and "I will read the file now." in result


def test_debug_agent_stops_after_replies_without_action():
    llm = make_llm(PROSE)
    assert DebugAgent(llm, max_iterations=50).run("bug").startswith("Stopped:")
    assert llm.chat.call_count == MAX_REPLIES_WITHOUT_ACTION


def test_a_working_reply_resets_the_count():
    llm = make_llm(PROSE, PROSE, READ, PROSE, PROSE, DONE)
    assert interactive()(llm, tool_system).run("task") == "finished"


def test_after_confirm_the_model_is_told_too():
    llm = make_llm(PROSE, DONE)
    agent = interactive()(llm, tool_system)
    assert agent.run_from_context({"task": "task", "history": [], "system": ""}) == "finished"
    check_told(llm)


def test_the_step_is_shown_to_the_model():
    import main
    from agent.core import no_action_step
    client = main.LLMClient("key", "model", "https://example.invalid", max_tokens=100)
    text = client._build_user_message({"task": "t", "history": [no_action_step(PROSE, 1)]})
    assert "Result: failed - Your last reply had no action" in text
