"""agent/test_memory_integration.py"""
import pytest
import tempfile
import os
from unittest.mock import MagicMock
from agent.core import InteractiveAgent
from agent.tool_system import tool_system


class TestMemoryIntegration:
    def test_agent_loads_memory_on_init(self):
        """The agent loads the memory when it starts"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"))
            os.makedirs(os.path.join(tmpdir, "tests"))

            mock_llm = MagicMock()
            mock_llm.chat.return_value = {
                "thought": "test",
                "action": {"tool": "read_file", "args": {"path": "main.py"}},
                "done": True,
                "summary": "done"
            }

            agent = InteractiveAgent(mock_llm, tool_system, project_path=tmpdir)

            assert agent.memory is not None
            assert agent.memory.data["structure"]["src_dir"] == "src"
            assert agent.memory.data["structure"]["test_dir"] == "tests"

    def test_memory_injected_in_context(self):
        """The memory is injected into the context"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"))

            mock_llm = MagicMock()
            mock_llm.chat.return_value = {
                "thought": "test",
                "action": None,
                "done": True,
                "summary": "done"
            }

            agent = InteractiveAgent(mock_llm, tool_system, project_path=tmpdir)
            context = agent._build_initial_context("test task")

            assert "memory" in context
            assert "src" in context["memory"]
            assert "## 项目记忆" in context["memory"]

    def test_no_memory_when_no_project_path(self):
        """No memory is loaded without project_path"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "thought": "test",
            "action": None,
            "done": True,
            "summary": "done"
        }

        agent = InteractiveAgent(mock_llm, tool_system, project_path=None)
        assert agent.memory is None

        context = agent._build_initial_context("test task")
        assert "memory" not in context
