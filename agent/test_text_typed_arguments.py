"""Numbers and true/false written as text ("60", "false") reach the tools as numbers and booleans.

The text reply format and /edit give every value as text when the model quotes it. Before,
exec(timeout="60") failed with a TypeError message, and use_regex="false" or create="false"
counted as true because a non-empty string is truthy.
"""
from typing import Optional

from agent.tool_system import ToolSystem, coerce_args
from agent.tools import register_tools


def options(count: int = 1, ratio: float = 0.5, on: bool = False, name: str = "x",
            limit: Optional[int] = None) -> dict:
    return {"success": True, "count": count, "ratio": ratio, "on": on, "name": name, "limit": limit}


def registered(fn):
    ts = ToolSystem()
    ts.register("tool", fn)
    return ts.get("tool").fn


def test_text_numbers_and_booleans_get_their_types():
    result = registered(options)(count="3", ratio="0.25", on="false", name="7", limit=" 5 ")
    assert result == {"success": True, "count": 3, "ratio": 0.25, "on": False, "name": "7", "limit": 5}
    assert registered(options)(on="True")["on"] is True


def test_values_that_already_have_the_type_are_kept():
    assert registered(options)(count=2, on=True) == {
        "success": True, "count": 2, "ratio": 0.5, "on": True, "name": "x", "limit": None}


def test_a_value_of_the_wrong_type_is_an_error_result():
    result = registered(options)(count="many")
    assert result["success"] is False
    assert "count must be a number, not 'many'" in result["error"]
    assert "Its arguments are: count, ratio, on, name, limit." in result["error"]
    result = registered(options)(on="maybe")
    assert result["success"] is False
    assert "on must be true or false" in result["error"]


def test_exec_takes_a_timeout_written_as_text():
    result = register_tools()["exec"](command="echo hi", timeout="5")
    assert result["success"] is True
    assert result["stdout"].strip() == "hi"


def test_use_regex_false_as_text_searches_for_plain_text(tmp_path):
    (tmp_path / "a.py").write_text("def (broken\n")
    result = register_tools()["search_files"](pattern="def (", path=str(tmp_path), use_regex="false")
    assert result["success"] is True
    assert result["count"] == 1


def test_coerce_args_still_rejects_unknown_arguments():
    try:
        coerce_args(options, {"colour": "red"})
    except ValueError as e:
        assert "'colour' is not an argument" in str(e)
    else:
        raise AssertionError("an unknown argument was accepted")
