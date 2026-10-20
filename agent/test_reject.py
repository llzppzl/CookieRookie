"""/reject with a reason keeps the task going (with a fake LLM, no real API calls)"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import LLMClient
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
import agent.tools as tools_module


class ScriptedLLM:
    """Returns scripted responses in order and records the context of each call"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(copy.deepcopy(context))
        return self.responses.pop(0)


def setup_module(module):
    tools_module.register_base_tools()


def test_reject_with_a_reason_goes_on_with_the_same_task(tmp_path):
    target = tmp_path / "test_calc.py"
    llm = ScriptedLLM([
        {"thought": "look around", "action": {"tool": "find_files", "args": {"pattern": "*.py", "path": str(tmp_path)}}, "done": False},
        {"thought": "write unittest tests", "action": {"tool": "write_file", "args": {"path": str(target), "content": "import unittest\n"}}, "done": False},
        {"thought": "write pytest tests", "action": {"tool": "write_file", "args": {"path": str(target), "content": "def test_add(): pass\n"}}, "done": False},
    ])
    agent = InteractiveAgent(llm, tool_system)

    assert agent.run("add tests for calc.py") == "awaiting_confirmation"
    assert agent.reject("use pytest, not unittest") == "awaiting_confirmation"

    # The rejected file was not written, and the next proposal is waiting
    assert not target.exists()
    assert agent.pending_action["tool_args"]["content"] == "def test_add(): pass\n"

    resumed = llm.contexts[-1]
    assert resumed["task"] == "add tests for calc.py"
    assert [h["action"]["tool"] for h in resumed["history"]] == ["find_files", "write_file"]
    declined = resumed["history"][-1]["result"]
    assert declined["success"] is False
    assert "use pytest, not unittest" in declined["error"]

    # The model reads the reason in its history
    message = LLMClient("dummy-key")._build_user_message(resumed)
    assert "use pytest, not unittest" in message


def test_reject_without_a_reason_stops_the_task(tmp_path):
    target = tmp_path / "x.py"
    llm = ScriptedLLM([
        {"thought": "write it", "action": {"tool": "write_file", "args": {"path": str(target), "content": "x"}}, "done": False},
    ])
    agent = InteractiveAgent(llm, tool_system)

    agent.run("write x.py")
    assert agent.reject() == "Rejected. Provide new instructions to continue."
    assert agent.pending_action is None
    assert not target.exists()
    assert len(llm.contexts) == 1


def test_reject_with_nothing_waiting():
    agent = InteractiveAgent(ScriptedLLM([]), tool_system)
    assert agent.reject("anything") == "No pending action to reject"
