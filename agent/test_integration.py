"""agent/test_integration.py"""
import pytest
from unittest.mock import MagicMock, patch
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
from agent import tools


class TestIntegration:
    def test_full_tool_system_setup(self):
        """测试完整工具系统初始化"""
        # 清空并重新注册
        from agent import tools as tools_module
        tools_module.register_base_tools()

        registered = tool_system.list_tools()
        assert "read_file" in registered
        assert "edit_file" in registered
        assert "write_file" in registered
        assert "exec" in registered
        assert "search_files" in registered
        assert "find_files" in registered

    def test_confirmable_flags(self):
        """测试 confirmable 标志"""
        from agent import tools as tools_module
        tools_module.register_base_tools()

        assert tool_system.is_confirmable("read_file") is False
        assert tool_system.is_confirmable("edit_file") is True
        assert tool_system.is_confirmable("write_file") is True
        assert tool_system.is_confirmable("exec") is True
        assert tool_system.is_confirmable("search_files") is False
        assert tool_system.is_confirmable("find_files") is False

    def test_interactive_agent_with_mock_llm(self):
        """测试 InteractiveAgent 与 mock LLM"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "thought": "test",
            "action": {"tool": "read_file", "args": {"path": "main.py"}},
            "done": False
        }

        from agent import tools as tools_module
        tools_module.register_base_tools()

        agent = InteractiveAgent(mock_llm, tool_system, max_iterations=1)
        result = agent.run("read main.py")

        assert result == "awaiting_confirmation"
        assert agent.pending_action is not None