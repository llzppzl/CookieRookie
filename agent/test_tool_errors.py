"""A tool that raises in interactive mode is reported to the model, as in debug mode, instead of
ending the task with a bare "Error: ..." in the terminal."""
from unittest.mock import MagicMock

from agent.core import InteractiveAgent
from agent.tool_system import ToolSystem

DONE = {"thought": "ok", "action": {}, "done": True, "summary": "finished"}


def make_llm(*replies):
    llm = MagicMock()
    llm.histories = []
    answers = iter(replies)

    def chat(context):
        llm.histories.append(list(context["history"]))
        return dict(next(answers))

    llm.chat.side_effect = chat
    return llm


def call(tool, **args):
    return {"thought": "try it", "action": {"tool": tool, "args": args}, "done": False}


def broken(framework: str = "pytest") -> dict:
    # Like test_generate(framework=None) from a tool-use call: the tool itself raises
    return {"success": True, "framework": framework.upper()}


def make_tools():
    tools = ToolSystem()
    tools.register("lookup", broken)
    tools.register("change", broken, confirmable=True)
    return tools


def check_reported(llm):
    result = llm.histories[1][-1]["result"]
    assert result["success"] is False
    assert "AttributeError" in result["error"]


def test_tool_that_raises_is_reported_and_the_task_goes_on():
    llm = make_llm(call("lookup", framework=None), DONE)
    assert InteractiveAgent(llm, make_tools()).run("task") == "finished"
    check_reported(llm)


def test_confirmed_tool_that_raises_is_reported_and_the_task_goes_on():
    llm = make_llm(call("change", framework=None), DONE)
    agent = InteractiveAgent(llm, make_tools())
    assert agent.run("task") == "awaiting_confirmation"
    assert agent.confirm() == "finished"
    assert agent.pending_action is None
    check_reported(llm)


def test_edited_tool_that_raises_is_reported_and_the_task_goes_on():
    llm = make_llm(call("change", framework="pytest"), DONE)
    agent = InteractiveAgent(llm, make_tools())
    assert agent.run("task") == "awaiting_confirmation"
    # /edit can only type text, so make the tool raise another way
    agent.pending_action["tool_args"]["framework"] = None
    assert agent.edit_and_confirm({}) == "finished"
    check_reported(llm)
