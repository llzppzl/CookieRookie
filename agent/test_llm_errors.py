"""agent/test_llm_errors.py - API errors and cut-off replies stop the run instead of being retried"""
import types

import requests

import main
from agent.core import DebugAgent, InteractiveAgent
from agent.tool_system import tool_system
import agent.tools as tools_module

tools_module.register_base_tools()


def fake_api(monkeypatch, *responses):
    """Make requests.post return these responses in order; returns the list of request bodies"""
    sent = []
    responses = list(responses)

    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        r = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(requests, "post", post)
    return sent


def reply(text, stop_reason="end_turn"):
    body = {"content": [{"type": "text", "text": text}], "stop_reason": stop_reason}
    return types.SimpleNamespace(status_code=200, json=lambda: body, text=text)


def error(status, text):
    return types.SimpleNamespace(status_code=status, text=text, json=lambda: {})


def client():
    return main.LLMClient("key", max_tokens=100)


def debug_context():
    return {"bug_report": "bug", "history": [], "system": ""}


def test_api_error_stops_interactive_run_after_one_call(monkeypatch):
    sent = fake_api(monkeypatch, error(401, '{"error": "invalid x-api-key"}'))
    agent = InteractiveAgent(client(), tool_system)
    agent._build_initial_context = lambda task: {**debug_context(), "task": task}

    result = agent.run("task")
    assert result.startswith("LLM error: API error: 401")
    assert "invalid x-api-key" in result
    assert len(sent) == 1


def test_api_error_stops_debug_run(monkeypatch):
    fake_api(monkeypatch, error(429, "quota exceeded"))
    result = DebugAgent(client()).run("bug")
    assert result == "LLM error: API error: 429 - quota exceeded"


def test_network_error_is_reported(monkeypatch):
    fake_api(monkeypatch, requests.ConnectionError("no route to host"))
    response = client().chat(debug_context())
    assert response["fatal"]
    assert response["error"].startswith("Could not reach https://api.minimax.io/anthropic")


def test_cut_off_reply_is_not_run(monkeypatch):
    fake_api(monkeypatch, reply('thought: t\naction: write_file(path="a.py", content="x = 1', "max_tokens"))
    response = client().chat(debug_context())
    assert response["fatal"]
    assert response["action"] is None
    assert "max_tokens=100" in response["error"]
    assert "MAX_TOKENS" in response["error"]


def test_unparseable_reply_is_still_retried(monkeypatch):
    sent = fake_api(monkeypatch, reply("Sure, let me look."),
                    reply("thought: done\naction:\ndone: true\nsummary: fixed"))
    agent = InteractiveAgent(client(), tool_system)
    agent._build_initial_context = lambda task: {**debug_context(), "task": task}
    assert agent.run("task") == "fixed"
    assert len(sent) == 2


def test_max_tokens_is_sent_and_configurable(monkeypatch, tmp_path):
    sent = fake_api(monkeypatch, reply("thought: done\naction:\ndone: true\nsummary: ok"))
    client().chat(debug_context())
    assert sent[0]["max_tokens"] == 100

    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=k\nMAX_TOKENS=16000\n", encoding="utf-8")
    monkeypatch.setattr(main, "PROJECT_DIR", str(tmp_path))
    assert main.load_config()["max_tokens"] == 16000
    assert main.LLMClient("k").max_tokens == 16000

    env.write_text("ANTHROPIC_API_KEY=k\nMAX_TOKENS=lots\n", encoding="utf-8")
    assert main.load_config()["max_tokens"] == main.DEFAULT_MAX_TOKENS
