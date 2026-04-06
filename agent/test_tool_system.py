"""agent/test_tool_system.py"""
import pytest
from agent.tool_system import ToolSystem, ToolDef


def dummy_echo(msg: str) -> dict:
    return {"msg": msg}


def dummy_modify(path: str) -> dict:
    return {"path": path}


class TestToolSystem:
    def test_register_and_get(self):
        ts = ToolSystem()
        ts.register("echo", dummy_echo, description="echo message")
        tool = ts.get("echo")
        assert tool is not None
        assert tool.name == "echo"
        assert tool.description == "echo message"

    def test_list_tools(self):
        ts = ToolSystem()
        ts.register("echo", dummy_echo)
        ts.register("modify", dummy_modify, confirmable=True)
        tools = ts.list_tools()
        assert len(tools) == 2
        assert tools["echo"].confirmable is False
        assert tools["modify"].confirmable is True

    def test_is_confirmable(self):
        ts = ToolSystem()
        ts.register("safe", dummy_echo)
        ts.register("danger", dummy_modify, confirmable=True)
        assert ts.is_confirmable("safe") is False
        assert ts.is_confirmable("danger") is True
        assert ts.is_confirmable("nonexistent") is False