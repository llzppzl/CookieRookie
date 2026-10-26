"""agent/test_read_outside_project.py - reading outside the project asks first

What the read tools return is sent to the API. They ran without asking for any path, so a
confused model, or instructions planted in a file it read, could send ~/.ssh/id_rsa to the API
and the user never saw it happen. Inside the project they still run without asking.
"""
import os

import pytest

from agent.core import DebugAgent, InteractiveAgent, preview_action
from agent.tool_system import tool_system
from agent.tools import register_base_tools


@pytest.fixture
def outside_file():
    # Not in pytest's tmp folders, which the tests treat as part of the project (conftest.py)
    path = os.path.join(os.path.dirname(os.path.realpath(os.getcwd())), "cookierookie-secret.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("SECRET=1\n")
    yield path
    os.remove(path)


@pytest.fixture(autouse=True)
def tools():
    register_base_tools()


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def chat(self, context):
        return self.replies.pop(0)


def call(tool, **args):
    return {"thought": "look", "action": {"tool": tool, "args": args}, "done": False}


DONE = {"thought": "", "action": {}, "done": True, "summary": "finished"}


@pytest.mark.parametrize("tool, arg", [("read_file", "path"), ("search_files", "path"),
                                       ("find_files", "path"), ("test_generate", "source")])
def test_a_read_tool_asks_only_outside_the_project(tool, arg, outside_file):
    assert tool_system.needs_confirmation(tool, {arg: outside_file})
    assert tool_system.needs_confirmation(tool, {arg: "/"})
    assert not tool_system.needs_confirmation(tool, {arg: "README.md" if tool != "search_files" else "agent"})


def test_the_default_folder_is_the_project():
    assert not tool_system.needs_confirmation("search_files", {"pattern": "x"})
    assert not tool_system.needs_confirmation("find_files", {"pattern": "*.py"})


def test_the_other_tools_ask_as_before():
    assert tool_system.needs_confirmation("exec", {"command": "ls"})
    assert tool_system.needs_confirmation("write_file", {"path": "a.py", "content": ""})
    assert not tool_system.needs_confirmation("no_such_tool", {})


def test_debug_mode_asks_before_reading_outside_and_a_no_reads_nothing(outside_file):
    asked = []

    def ask(tool_name, args):
        asked.append((tool_name, args))
        return "no", ""

    llm = ScriptedLLM(call("read_file", path=outside_file), call("read_file", path="README.md"), DONE)
    agent = DebugAgent(llm, ask=ask)
    context_seen = []
    original_chat = llm.chat
    llm.chat = lambda context: context_seen.append(context) or original_chat(context)
    agent.run("bug")
    assert asked == [("read_file", {"path": outside_file})]
    history = context_seen[-1]["history"]
    assert "declined" in history[0]["result"]["error"]
    assert history[1]["result"]["success"] is True


def test_interactive_mode_waits_for_confirm_before_reading_outside(outside_file):
    agent = InteractiveAgent(ScriptedLLM(call("read_file", path=outside_file), DONE), tool_system)
    assert agent.run("read it") == "awaiting_confirmation"
    assert agent.pending_action["tool_name"] == "read_file"


def test_interactive_mode_reads_inside_the_project_without_asking():
    agent = InteractiveAgent(ScriptedLLM(call("read_file", path="README.md"), DONE), tool_system)
    assert agent.run("read it") == "finished"


def test_the_preview_says_the_read_is_outside_the_project(outside_file):
    text = preview_action("read_file", {"path": outside_file})
    assert "Read outside the project folder" in text
    assert outside_file in text
