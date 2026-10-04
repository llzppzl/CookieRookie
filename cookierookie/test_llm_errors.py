"""cookierookie/test_llm_errors.py - API 报错和输出截断时的行为（mock HTTP，不调用真实 API）"""
from unittest.mock import MagicMock

import pytest

from cookierookie import cli
from cookierookie.core import InteractiveAgent
from cookierookie.tool_system import tool_system
import cookierookie.tools as tools_module


def setup_module(module):
    tools_module.register_base_tools()


def fake_response(status_code=200, body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body or {}
    response.text = text
    return response


@pytest.fixture
def post(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(cli.requests, "post", mock)
    return mock


def context():
    return {"task": "write a big file", "history": [], "system": ""}


def test_default_max_tokens_is_sent(post):
    post.return_value = fake_response(body={"content": [{"type": "text", "text": "thought: ok\ndone: true"}]})

    cli.LLMClient("key").chat(context())

    assert post.call_args.kwargs["json"]["max_tokens"] == cli.DEFAULT_MAX_TOKENS


def test_truncated_reply_is_reported_not_parsed(post):
    post.return_value = fake_response(body={
        "stop_reason": "max_tokens",
        "content": [{"type": "text", "text": 'thought: write it\naction: write_file(path="a.py", content="def f(): ...'}],
    })

    result = cli.LLMClient("key", max_tokens=100).chat(context())

    assert result["action"] is None
    assert result["fatal"] is True
    assert "max_tokens=100" in result["error"]


def test_agent_stops_after_one_call_on_api_error(post):
    """key 错误时只请求一次并把错误告诉用户，而不是静默重试 50 次"""
    post.return_value = fake_response(status_code=401, text='{"error": "invalid api key"}')
    agent = InteractiveAgent(cli.LLMClient("bad-key"), tool_system)

    result = agent.run("write hello.py")

    assert post.call_count == 1
    assert "401" in result
    assert "invalid api key" in result


def test_agent_still_retries_when_reply_cannot_be_parsed():
    llm = MagicMock()
    llm.chat.side_effect = [
        {"action": None, "error": "Failed to parse: ...", "raw": "..."},
        {"thought": "done", "action": {}, "done": True, "summary": "ok"},
    ]
    agent = InteractiveAgent(llm, tool_system)

    assert agent.run("say hi") == "ok"
    assert llm.chat.call_count == 2


def test_max_tokens_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "USER_CONFIG", tmp_path / "none.env")
    monkeypatch.setattr(cli, "REPO_DIR", tmp_path)
    monkeypatch.setenv("MAX_TOKENS", "16000")

    assert cli.load_config()["max_tokens"] == 16000


def test_invalid_max_tokens_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "USER_CONFIG", tmp_path / "none.env")
    monkeypatch.setattr(cli, "REPO_DIR", tmp_path)
    monkeypatch.setenv("MAX_TOKENS", "lots")

    assert cli.load_config()["max_tokens"] == cli.DEFAULT_MAX_TOKENS
