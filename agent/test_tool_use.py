"""agent/test_tool_use.py - tools are offered through the API's tool use, with the text format as a fallback"""
import types
from typing import List, Optional

import requests

import main
from agent.core import DebugAgent, InteractiveAgent
from agent.tool_system import ToolSystem, schema_from_signature, tool_system
import agent.tools as tools_module

tools_module.register_base_tools()


def fake_api(monkeypatch, *responses):
    """Make requests.post return these responses in order; returns the list of request bodies"""
    sent = []
    responses = list(responses)

    def post(url, headers=None, json=None, timeout=None):
        sent.append(dict(json))
        return responses.pop(0) if len(responses) > 1 else responses[0]

    monkeypatch.setattr(requests, "post", post)
    return sent


def answer(*blocks, stop_reason="end_turn"):
    body = {"content": list(blocks), "stop_reason": stop_reason}
    return types.SimpleNamespace(status_code=200, json=lambda: body, text=str(body))


def text(t):
    return {"type": "text", "text": t}


def tool_use(name, args):
    return {"type": "tool_use", "id": "toolu_1", "name": name, "input": args}


def refused(status=400):
    return types.SimpleNamespace(status_code=status, text='{"error": "tools are not supported"}', json=lambda: {})


def context(tools=None):
    return {"task": "task", "history": [], "system": "", "tools": tools}


def client():
    return main.LLMClient("key", max_tokens=100)


def commit(message: str, files: Optional[List[str]] = None, amend: bool = False):
    return {}


def test_schema_from_the_signature():
    schema = schema_from_signature(commit)
    assert schema["required"] == ["message"]
    assert schema["properties"] == {
        "message": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "amend": {"type": "boolean"},
    }


def test_registered_tools_keep_their_real_arguments():
    specs = {s["name"]: s for s in tool_system.api_tools()}
    read = specs["read_file"]["input_schema"]
    assert read["required"] == ["path"]
    assert read["properties"]["limit"] == {"type": "integer"}
    for spec in specs.values():
        assert spec["description"]
        assert not any(0x4e00 <= ord(c) <= 0x9fff for c in spec["description"])


def test_api_tools_can_be_limited_to_some_names():
    assert [s["name"] for s in tool_system.api_tools(["exec"])] == ["exec"]


def test_tool_call_runs_with_its_arguments_as_sent(monkeypatch):
    content = 'def f():\n    return "a\\nb"\n'
    sent = fake_api(monkeypatch, answer(text("Write the file."), tool_use("write_file", {"path": "f.py", "content": content}),
                                        stop_reason="tool_use"))
    parsed = client().chat(context(tool_system.api_tools()))
    assert sent[0]["tools"]
    assert parsed["action"] == {"tool": "write_file", "args": {"path": "f.py", "content": content}}
    assert parsed["thought"] == "Write the file."
    assert parsed["done"] is False


def test_text_format_still_works_with_tools_offered(monkeypatch):
    fake_api(monkeypatch, answer(text('thought: read\naction: read_file(path="a.py")\ndone: false')))
    parsed = client().chat(context(tool_system.api_tools()))
    assert parsed["action"] == {"tool": "read_file", "args": {"path": "a.py"}}


def test_prose_answer_with_tools_offered_is_the_final_answer(monkeypatch):
    fake_api(monkeypatch, answer(text("I fixed the off-by-one error in loop.py.")))
    parsed = client().chat(context(tool_system.api_tools()))
    assert parsed["done"] is True
    assert parsed["summary"] == "I fixed the off-by-one error in loop.py."


def test_prose_answer_without_tools_is_not_taken_as_done(monkeypatch):
    sent = fake_api(monkeypatch, answer(text("I fixed it.")))
    parsed = client().chat(context())
    assert "tools" not in sent[0]
    assert not parsed.get("done")


def test_api_that_refuses_tools_is_asked_again_without_them(monkeypatch):
    sent = fake_api(monkeypatch, refused(), answer(text('thought: read\naction: read_file(path="a.py")\ndone: false')))
    llm = client()
    parsed = llm.chat(context(tool_system.api_tools()))
    assert "tools" in sent[0] and "tools" not in sent[1]
    assert parsed["action"]["tool"] == "read_file"
    # And the rest of the session doesn't send them again
    llm.chat(context(tool_system.api_tools()))
    assert "tools" not in sent[2]


def test_other_errors_are_not_retried(monkeypatch):
    sent = fake_api(monkeypatch, refused(401))
    parsed = client().chat(context(tool_system.api_tools()))
    assert len(sent) == 1
    assert parsed["fatal"]


def test_debug_mode_offers_its_tools():
    agent = DebugAgent(client())
    names = [s["name"] for s in agent._build_initial_context("bug")["tools"]]
    assert sorted(names) == sorted(agent.tools)


def test_interactive_mode_offers_tools_but_planning_does_not():
    ts = ToolSystem()
    ts.register("read_thing", lambda path: {"success": True}, description="Read a thing")
    llm = types.SimpleNamespace(calls=[])
    llm.chat = lambda ctx: (llm.calls.append(ctx), {"thought": "t", "action": {}, "done": True, "summary": "ok"})[1]
    agent = InteractiveAgent(llm, ts)
    agent.run("task")
    assert [s["name"] for s in llm.calls[0]["tools"]] == ["read_thing"]
    agent.plan("task")
    assert not llm.calls[1].get("tools")
