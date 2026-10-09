"""Wrong tool arguments come back to the model as an error result instead of ending the task."""
from unittest.mock import MagicMock

from agent.core import InteractiveAgent, DebugAgent
from agent.tool_system import ToolSystem


def read_thing(path: str, offset: int = 1, limit: int = 100) -> dict:
    return {"success": True, "path": path, "offset": offset, "limit": limit}


def broken(path: str) -> dict:
    raise TypeError("a real bug inside the tool")


def test_right_arguments_still_work():
    ts = ToolSystem()
    ts.register("read_thing", read_thing)
    assert ts.get("read_thing").fn(path="a.py", limit=5) == {
        "success": True, "path": "a.py", "offset": 1, "limit": 5}


def test_wrong_argument_is_an_error_result():
    ts = ToolSystem()
    ts.register("read_thing", read_thing)
    result = ts.get("read_thing").fn(file_path="a.py")
    assert result["success"] is False
    assert "unknown argument 'file_path'" in result["error"]
    assert "Its arguments are: path, offset, limit." in result["error"]


def test_missing_argument_is_an_error_result():
    ts = ToolSystem()
    ts.register("read_thing", read_thing)
    result = ts.get("read_thing").fn()
    assert result["success"] is False
    assert "'path'" in result["error"]


def test_tools_with_kwargs_take_any_argument():
    ts = ToolSystem()
    ts.register("anything", lambda **kw: {"success": True, **kw})
    assert ts.get("anything").fn(a=1) == {"success": True, "a": 1}


def test_errors_inside_the_tool_are_not_hidden():
    ts = ToolSystem()
    ts.register("broken", broken)
    try:
        ts.get("broken").fn(path="x")
    except TypeError as e:
        assert "real bug" in str(e)
    else:
        raise AssertionError("the tool's own TypeError was swallowed")


def test_interactive_task_continues_after_wrong_argument():
    ts = ToolSystem()
    ts.register("read_thing", read_thing)
    llm = MagicMock()
    llm.chat.side_effect = [
        {"thought": "read", "action": {"tool": "read_thing", "args": {"file_path": "a.py"}}, "done": False},
        {"thought": "fix the name", "action": {"tool": "read_thing", "args": {"path": "a.py"}}, "done": False},
        {"thought": "done", "action": {}, "done": True, "summary": "read a.py"},
    ]
    agent = InteractiveAgent(llm, ts)
    assert agent.run("read a.py") == "read a.py"
    history = llm.chat.call_args.args[0]["history"]
    assert history[0]["result"]["success"] is False
    assert history[1]["result"]["path"] == "a.py"


def test_debug_mode_continues_after_wrong_argument(tmp_path):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    llm = MagicMock()
    llm.chat.side_effect = [
        {"thought": "read", "action": {"tool": "read_file", "args": {"file": str(target)}}, "done": False},
        {"thought": "done", "action": {}, "done": True, "summary": "nothing to fix"},
    ]
    agent = DebugAgent(llm)
    assert agent.run("bug") == "nothing to fix"
    history = llm.chat.call_args.args[0]["history"]
    assert "unknown argument 'file'" in history[0]["result"]["error"]
