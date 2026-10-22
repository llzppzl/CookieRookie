"""max_iterations counts the model replies of a whole task, across /confirm, /reject and /edit"""

from unittest.mock import MagicMock

from agent.core import InteractiveAgent
from agent.tool_system import ToolSystem


def reply(tool, **args):
    return {"thought": f"use {tool}", "action": {"tool": tool, "args": args}, "done": False, "raw": ""}


def make_agent(replies, max_iterations=4):
    ts = ToolSystem()
    ts.register("look", lambda: {"success": True}, confirmable=False)
    ts.register("change", lambda value="": {"success": True, "value": value}, confirmable=True)
    llm = MagicMock()
    llm.chat.side_effect = replies
    return InteractiveAgent(llm, ts, max_iterations=max_iterations), llm


def test_confirm_does_not_restart_the_count():
    # Before: the task got max_iterations replies before /confirm and max_iterations more after it
    agent, llm = make_agent([reply("look"), reply("change")] + [reply("look")] * 10)
    assert agent.run("task") == "awaiting_confirmation"
    assert agent.confirm() == "Max iterations reached"
    assert llm.chat.call_count == 4


def test_steps_are_numbered_once_over_the_whole_task():
    # Before: the history went Step 1, Step 2, Step confirmed, Step 1, ... after each /confirm
    agent, llm = make_agent([reply("look"), reply("change"), reply("look"), reply("change", value="x"),
                             {"thought": "", "action": {}, "done": True, "summary": "all done", "raw": ""}],
                            max_iterations=10)
    assert agent.run("task") == "awaiting_confirmation"
    assert agent.confirm() == "awaiting_confirmation"
    assert agent.edit_and_confirm({"value": "y"}) == "all done"
    history = llm.chat.call_args.args[0]["history"]
    assert [step["iteration"] for step in history] == [1, 2, 3, 4]


def test_reject_with_a_reason_keeps_the_count():
    agent, llm = make_agent([reply("change"), reply("change"), reply("look"), reply("look")], max_iterations=3)
    assert agent.run("task") == "awaiting_confirmation"
    assert agent.reject("not that") == "awaiting_confirmation"
    assert agent.reject("still not that") == "Max iterations reached"
    assert llm.chat.call_count == 3


def test_a_new_task_gets_a_new_count():
    agent, llm = make_agent([reply("look")] * 4, max_iterations=2)
    assert agent.run("first") == "Max iterations reached"
    assert agent.run("second") == "Max iterations reached"
    assert llm.chat.call_count == 4
