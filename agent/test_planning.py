"""agent/test_planning.py"""
import pytest
from unittest.mock import MagicMock
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
import agent.tools as tools_module


class TestPlanning:
    @classmethod
    def setup_class(cls):
        """注册基础工具"""
        tools_module.register_base_tools()

    def test_format_plan(self):
        """测试 Plan 格式化"""
        agent = InteractiveAgent(MagicMock(), tool_system)

        plan = {
            "summary": "测试任务",
            "steps": [
                {"step": 1, "tool": "read_file", "description": "读取文件", "confirmable": False},
                {"step": 2, "tool": "edit_file", "description": "编辑文件", "confirmable": True},
            ]
        }

        formatted = agent._format_plan(plan)
        assert "## 执行计划" in formatted
        assert "1. [read_file] 读取文件" in formatted
        assert "2. [edit_file] 编辑文件 ✅ 需要确认" in formatted

    def test_parse_plan_response(self):
        """测试解析 Plan 响应"""
        agent = InteractiveAgent(MagicMock(), tool_system)

        response = """
plan: true
summary: 测试任务
steps:
  1. [read_file] 读取文件
  2. [write_file] 创建文件
"""
        plan = agent._parse_plan_response(response)
        assert plan["summary"] == "测试任务"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["tool"] == "read_file"
        assert plan["steps"][0]["confirmable"] is False
        assert plan["steps"][1]["tool"] == "write_file"
        assert plan["steps"][1]["confirmable"] is True  # write_file is confirmable

    def test_skip_step_method_exists(self):
        """测试 skip_step 方法存在"""
        agent = InteractiveAgent(MagicMock(), tool_system)
        assert hasattr(agent, 'skip_step')

    def test_execute_plan_method_exists(self):
        """测试 execute_plan 方法存在"""
        agent = InteractiveAgent(MagicMock(), tool_system)
        assert hasattr(agent, 'execute_plan')

    def test_plan_method_exists(self):
        """测试 plan 方法存在"""
        agent = InteractiveAgent(MagicMock(), tool_system)
        assert hasattr(agent, 'plan')