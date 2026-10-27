"""agent/test_exit_codes.py - the command's exit code says whether the run worked"""
import pytest

import main


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, context):
        return self.reply


FIXED = {"thought": "", "action": {}, "done": True, "summary": "fixed it", "raw": "done: true"}
API_ERROR = {"action": None, "fatal": True, "raw": "", "error": "API error: 401 - bad key"}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda *a, **k: {"api_key": "k", "model": "m", "base_url": "u",
                                                               "max_tokens": 100})


def use_model(monkeypatch, reply):
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: FakeLLM(reply))


def cli(monkeypatch, *args):
    """main.cli(args) as `python main.py args` runs it: main() reads sys.argv itself"""
    monkeypatch.setattr(main.sys, "argv", ["main.py", *args])
    return main.cli(list(args))


def test_a_fixed_bug_exits_with_0(configured, monkeypatch):
    use_model(monkeypatch, FIXED)
    assert cli(monkeypatch, "the bug") == 0


def test_a_run_that_stops_on_an_error_exits_with_1(configured, monkeypatch, capsys):
    # Before: 0, so a script or CI job running cookierookie could not see that it failed
    use_model(monkeypatch, API_ERROR)
    assert cli(monkeypatch, "the bug") == 1
    assert "API error: 401" in capsys.readouterr().out


def test_no_api_key_exits_with_1(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda *a, **k: {"api_key": None, "model": "m", "base_url": "u",
                                                               "max_tokens": 100})
    assert cli(monkeypatch, "the bug") == 1
    assert cli(monkeypatch, "--interactive") == 1


def test_usage_without_a_bug_report_exits_with_0(monkeypatch):
    monkeypatch.delenv("DEBUG_BUG_REPORT", raising=False)
    assert cli(monkeypatch) == 0
