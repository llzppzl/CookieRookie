"""cookierookie/test_interactive_flow.py - 交互模式端到端流程（用假 LLM，不调用真实 API）"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cookierookie.cli import LLMClient
from cookierookie.core import InteractiveAgent
from cookierookie.tool_system import tool_system
import cookierookie.tools as tools_module


class ScriptedLLM:
    """按顺序返回预设响应，并记录每次调用时收到的 context"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(copy.deepcopy(context))
        return self.responses.pop(0)


def setup_module(module):
    tools_module.register_base_tools()


def test_user_message_accepts_interactive_context():
    """交互模式的 context 只有 task，没有 bug_report，不应该报 KeyError"""
    agent = InteractiveAgent(ScriptedLLM([]), tool_system)
    context = agent._build_initial_context("write hello.py")

    message = LLMClient("dummy-key")._build_user_message(context)

    assert "## Task" in message
    assert "write hello.py" in message


def test_user_message_still_supports_debug_mode():
    context = {"bug_report": "division by zero", "history": [], "system": ""}

    message = LLMClient("dummy-key")._build_user_message(context)

    assert "## Bug Report" in message
    assert "division by zero" in message


def test_confirm_keeps_task_and_history(tmp_path):
    """确认危险操作后，Agent 应该带着原任务和之前的历史继续，而不是从空白开始"""
    target = tmp_path / "hello.py"
    llm = ScriptedLLM([
        {"thought": "look around", "action": {"tool": "find_files", "args": {"pattern": "*.py", "path": str(tmp_path)}}, "done": False},
        {"thought": "create the file", "action": {"tool": "write_file", "args": {"path": str(target), "content": "print('hi')\n"}}, "done": False},
        {"thought": "finished", "action": {}, "done": True, "summary": "created hello.py"},
    ])
    agent = InteractiveAgent(llm, tool_system)

    assert agent.run("write hello.py") == "awaiting_confirmation"
    assert agent.confirm() == "created hello.py"

    assert target.read_text() == "print('hi')\n"
    resumed = llm.contexts[-1]
    assert resumed["task"] == "write hello.py"
    assert [h["action"]["tool"] for h in resumed["history"]] == ["find_files", "write_file"]


def test_edit_and_confirm_keeps_task(tmp_path):
    target = tmp_path / "hello.py"
    llm = ScriptedLLM([
        {"thought": "create the file", "action": {"tool": "write_file", "args": {"path": str(target), "content": "x"}}, "done": False},
        {"thought": "finished", "action": {}, "done": True, "summary": "done"},
    ])
    agent = InteractiveAgent(llm, tool_system)

    agent.run("write hello.py")
    agent.edit_and_confirm({"path": str(target), "content": "y"})

    assert target.read_text() == "y"
    assert llm.contexts[-1]["task"] == "write hello.py"
