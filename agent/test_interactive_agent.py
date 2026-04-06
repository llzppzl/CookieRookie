"""agent/test_interactive_agent.py"""
import pytest
from unittest.mock import MagicMock


class MockToolSystem:
    def __init__(self):
        self.tools = {}
        self.confirmable_map = {}

    def register(self, name, fn, confirmable=False, description="", args_schema=None):
        self.tools[name] = fn
        self.confirmable_map[name] = confirmable

    def get(self, name):
        return MagicMock(fn=self.tools.get(name)) if name in self.tools else None

    def list_tools(self):
        return {name: MagicMock(fn=fn, confirmable=self.confirmable_map.get(name, False),
                                description="")
                for name, fn in self.tools.items()}

    def is_confirmable(self, name):
        return self.confirmable_map.get(name, False)


class TestInteractiveAgent:
    def test_initialization(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        agent = InteractiveAgent(mock_llm, mock_ts, max_iterations=10)
        assert agent.llm == mock_llm
        assert agent.tool_system == mock_ts
        assert agent.max_iterations == 10
        assert agent.pending_action is None

    def test_build_tool_list(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("read_file", lambda x: x, confirmable=False, description="read file")
        mock_ts.register("edit_file", lambda x: x, confirmable=True, description="edit file")
        agent = InteractiveAgent(mock_llm, mock_ts)
        tool_list = agent._build_tool_list()
        assert "read_file" in tool_list
        assert "edit_file [需要确认]" in tool_list

    def test_pending_action_flow(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("exec", lambda cmd: {"success": True}, confirmable=True, description="execute")
        agent = InteractiveAgent(mock_llm, mock_ts)
        mock_llm.chat.return_value = {
            "thought": "need to execute command",
            "action": {"tool": "exec", "args": {"command": "rm -rf /"}},
            "done": False
        }
        result = agent.run("test task")
        assert result == "awaiting_confirmation"
        assert agent.pending_action is not None
        assert agent.pending_action["action"]["tool"] == "exec"

    def test_non_confirmable_tool_execution(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("read", lambda path: {"content": "file content"}, confirmable=False, description="read file")
        agent = InteractiveAgent(mock_llm, mock_ts)
        # First call returns done=False (loops), but we just verify execution worked
        mock_llm.chat.return_value = {
            "thought": "need to read file",
            "action": {"tool": "read", "args": {"path": "test.py"}},
            "done": False
        }
        result = agent.run("test task")
        # Since done=False always, it reaches max iterations
        assert result == "Max iterations reached"
        # Verify chat was called multiple times (loop ran)
        assert mock_llm.chat.call_count == 50

    def test_confirm_method(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("exec", lambda cmd: {"success": True}, confirmable=True, description="execute")
        agent = InteractiveAgent(mock_llm, mock_ts)

        # 先设置一个 pending_action
        agent.pending_action = {
            "thought": "need to execute command",
            "action": {"tool": "exec", "args": {"cmd": "echo hello"}},
            "tool_name": "exec",
            "tool_args": {"cmd": "echo hello"}
        }

        # 设置后续调用返回 done
        mock_llm.chat.return_value = {
            "thought": "task done",
            "action": None,
            "done": True,
            "summary": "completed"
        }

        result = agent.confirm()
        assert agent.pending_action is None

    def test_reject_method(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        agent = InteractiveAgent(mock_llm, mock_ts)

        agent.pending_action = {
            "thought": "need to execute command",
            "action": {"tool": "exec", "args": {"command": "rm -rf /"}},
            "tool_name": "exec",
            "tool_args": {"command": "rm -rf /"}
        }

        result = agent.reject()
        assert agent.pending_action is None
        assert "Rejected" in result

    def test_edit_and_confirm_method(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("exec", lambda cmd: {"success": True}, confirmable=True, description="execute")
        agent = InteractiveAgent(mock_llm, mock_ts)

        agent.pending_action = {
            "thought": "need to execute command",
            "action": {"tool": "exec", "args": {"cmd": "rm -rf /"}},
            "tool_name": "exec",
            "tool_args": {"cmd": "rm -rf /"}
        }

        mock_llm.chat.return_value = {
            "thought": "done",
            "action": None,
            "done": True,
            "summary": "completed"
        }

        modified_args = {"cmd": "echo safe"}
        result = agent.edit_and_confirm(modified_args)
        assert agent.pending_action is None

    def test_show_pending_action(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        agent = InteractiveAgent(mock_llm, mock_ts)

        agent.pending_action = {
            "thought": "need to delete system",
            "action": {"tool": "exec", "args": {"command": "rm -rf /", "force": True}},
            "tool_name": "exec",
            "tool_args": {"command": "rm -rf /", "force": True}
        }

        # Should not raise any exceptions
        agent._show_pending_action()

    def test_done_returns_summary(self):
        from agent.core import InteractiveAgent
        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("read", lambda path: {"content": "content"}, confirmable=False, description="read")
        agent = InteractiveAgent(mock_llm, mock_ts)

        mock_llm.chat.return_value = {
            "thought": "task completed",
            "action": None,
            "done": True,
            "summary": "All done!"
        }

        result = agent.run("test task")
        assert result == "All done!"