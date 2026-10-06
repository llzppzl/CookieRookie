"""cookierookie/test_tool_calling.py - tools offered through the API's tool use (mock HTTP, no API calls)"""
import inspect
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from cookierookie import cli
from cookierookie.core import DebugAgent, InteractiveAgent, approve_all
from cookierookie.tool_system import schema_from_signature, tool_system
import cookierookie.tools as tools_module


def setup_module(module):
    tools_module.register_base_tools()


def reply(*blocks, stop_reason="end_turn"):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"content": list(blocks), "stop_reason": stop_reason}
    return response


def text(value):
    return {"type": "text", "text": value}


def tool_use(name, **args):
    return {"type": "tool_use", "id": f"toolu_{name}", "name": name, "input": args}


@pytest.fixture
def post(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(cli.requests, "post", mock)
    return mock


def sent(post, call=-1):
    """The JSON body of a request the client sent"""
    return post.call_args_list[call].kwargs["json"]


# ---------- what is sent ----------

def test_interactive_mode_offers_every_tool_with_a_schema(post):
    post.return_value = reply(text("Nothing to do."))

    InteractiveAgent(cli.LLMClient("key"), tool_system).run("say hi")

    tools = {tool["name"]: tool for tool in sent(post)["tools"]}
    assert {"read_file", "edit_file", "write_file", "exec", "test_run"} <= set(tools)
    assert tools["write_file"]["input_schema"]["required"] == ["path", "content"]
    assert "asked first" in tools["exec"]["description"]


def test_debug_mode_offers_only_the_tools_it_runs():
    context = DebugAgent(MagicMock(), ask=approve_all)._build_initial_context("it crashes")

    assert [tool["name"] for tool in context["tools"]] == \
        ["read_file", "edit_file", "write_file", "exec", "search_files", "find_files"]


def test_planning_offers_no_tools(post):
    post.return_value = reply(text("plan: true\nsummary: say hi\nsteps:\n  1. [write_file] create hi.py"))

    plan = InteractiveAgent(cli.LLMClient("key"), tool_system).plan("say hi")

    assert "tools" not in sent(post)
    assert plan["steps"][0]["tool"] == "write_file"


# ---------- reading the reply ----------

def test_a_tool_call_becomes_the_action(post):
    post.return_value = reply(text("Let me look at the file."), tool_use("read_file", path="app.py", limit=20))

    result = cli.LLMClient("key").chat({"task": "t", "history": [], "system": "", "tools": [{"name": "read_file"}]})

    assert result["action"] == {"tool": "read_file", "args": {"path": "app.py", "limit": 20}}
    assert result["thought"] == "Let me look at the file."
    assert result["done"] is False


def test_only_the_first_of_several_tool_calls_runs(post):
    post.return_value = reply(tool_use("read_file", path="a.py"), tool_use("read_file", path="b.py"))

    result = cli.LLMClient("key").chat({"task": "t", "history": [], "system": "", "tools": [{"name": "read_file"}]})

    assert result["action"]["args"] == {"path": "a.py"}


def test_a_reply_without_a_tool_call_finishes_the_task(post):
    post.return_value = reply(text("x was never set. I set it to 10 on line 1."))
    agent = InteractiveAgent(cli.LLMClient("key"), tool_system)

    assert agent.run("fix x") == "x was never set. I set it to 10 on line 1."
    assert post.call_count == 1


def test_file_content_with_quotes_backslashes_and_newlines_is_written_exactly(post, tmp_path):
    target = tmp_path / "greet.py"
    content = 'def greet(name):\n    print(f"Hello, {name}!\\n")  # it\'s "quoted"\n    return r"C:\\path"\n'
    post.side_effect = [
        reply(text("Create the file."), tool_use("write_file", path=str(target), content=content)),
        reply(text("Created greet.py.")),
    ]
    agent = InteractiveAgent(cli.LLMClient("key"), tool_system)

    assert agent.run("write greet.py") == "awaiting_confirmation"
    assert agent.confirm() == "Created greet.py."

    assert target.read_text() == content


def test_a_reply_in_the_text_format_still_works(post):
    post.return_value = reply(text('thought: read it first\naction: read_file(path="app.py", limit=5)\ndone: false'))

    result = cli.LLMClient("key").chat({"task": "t", "history": [], "system": "", "tools": [{"name": "read_file"}]})

    assert result["action"] == {"tool": "read_file", "args": {"path": "app.py", "limit": 5}}


def test_text_format_arguments_are_read_like_python():
    client = cli.LLMClient("key")

    parsed = client._parse_response(
        'Thought: write it\n'
        'Action: write_file(path="a.py", content="x = \\"a\\"\\nprint(x)\\n")\n'
        'done: false')
    assert parsed["action"]["args"] == {"path": "a.py", "content": 'x = "a"\nprint(x)\n'}

    # A string over several lines isn't valid Python; the older patterns still read it
    parsed = client._parse_response('thought: write it\naction: write_file(path="a.py", content="one\ntwo")\ndone: false')
    assert parsed["action"]["args"] == {"path": "a.py", "content": "one\ntwo"}


def test_text_format_thought_stops_at_the_next_label():
    parsed = cli.LLMClient("key")._parse_response("thought: finished\ndone: true\nsummary: set x to 10")

    assert parsed["thought"] == "finished"
    assert parsed["done"] is True
    assert parsed["summary"] == "set x to 10"


# ---------- the history the model reads ----------

def message_after(*history):
    return cli.LLMClient("key")._build_user_message({"task": "t", "history": list(history)})


def test_history_shows_why_a_command_failed():
    message = message_after({
        "action": {"tool": "exec", "args": {"command": "python -m pytest"}},
        "result": {"success": False, "returncode": 1, "stdout": "FAILED test_app.py::test_x - assert 1 == 10", "stderr": ""},
        "thought": "run the tests", "iteration": 1,
    })

    assert "exited with code 1" in message
    assert "assert 1 == 10" in message


def test_history_shortens_long_arguments_and_shows_the_users_answer():
    message = message_after({
        "action": {"tool": "write_file", "args": {"path": "big.py", "content": "x = 1\n" * 1000}},
        "result": {"success": False, "error": "The user declined this action."},
        "thought": "", "iteration": "rejected",
    })

    assert "6000 characters in total" in message
    assert len(message) < 1000
    assert "### Step 1 (the user declined it)" in message


def test_history_shows_the_end_of_a_test_run():
    output = "tests/test_calc.py::test_ok PASSED\n" * 200 + \
        "FAILED tests/test_calc.py::test_add - assert 3 == 4\n1 failed, 200 passed in 0.52s\n"
    message = message_after({
        "action": {"tool": "test_run", "args": {}},
        "result": {"success": False, "returncode": 1, "framework": "pytest", "command": "python -m pytest -v",
                   "stdout": output, "stderr": "", "passed": 200, "failed": 1, "errors": 0},
        "thought": "", "iteration": 1,
    })

    assert "python -m pytest -v exited with code 1 (passed: 200, failed: 1)." in message
    assert "assert 3 == 4" in message
    assert "1 failed, 200 passed" in message
    assert len(message) < 3000


# ---------- schemas ----------

def test_schema_from_signature():
    def tool(path: str, line: Optional[int] = None, names: List[str] = None, force: bool = False, note=""):
        pass

    assert schema_from_signature(tool) == {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "line": {"type": "integer"},
            "names": {"type": "array"},
            "force": {"type": "boolean"},
            "note": {"type": "string"},
        },
        "required": ["path"],
    }


def test_a_tool_registered_without_a_schema_gets_one_from_its_signature():
    from cookierookie.tool_system import ToolSystem

    def count_lines(path: str, limit: int = 10) -> dict:
        """Count the lines of a file.

        More details the model doesn't need."""

    tools = ToolSystem()
    tools.register("count_lines", count_lines)

    assert tools.api_tools() == [{
        "name": "count_lines",
        "description": "Count the lines of a file.",
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
                         "required": ["path"]},
    }]


@pytest.mark.parametrize("name", ["read_file", "edit_file", "write_file", "exec", "search_files",
                                  "find_files", "test_run", "test_generate"])
def test_each_tool_schema_matches_the_function(name):
    tool = tool_system.get(name)
    schema = next(spec for spec in tool_system.api_tools() if spec["name"] == name)["input_schema"]
    params = inspect.signature(tool.fn).parameters

    assert set(schema["properties"]) == set(params)
    assert set(schema["required"]) <= set(params)
    assert {p for p, param in params.items() if param.default is param.empty} <= set(schema["required"])
    assert all(prop.get("description") for prop in schema["properties"].values())
