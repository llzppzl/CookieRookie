"""The history the model reads stays bounded on long tasks"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.history import FULL_STEPS, compact_history
from main import LLMClient

BIG = "x = 1\n" * 5000


def read_step(i):
    return {
        "action": {"tool": "read_file", "args": {"path": f"file{i}.py"}},
        "result": {"success": True, "content": BIG, "lines": "1-100", "total": 5000},
        "thought": f"read file {i}",
        "iteration": i,
    }


def exec_step(i):
    return {
        "action": {"tool": "exec", "args": {"command": "pytest"}},
        "result": {"success": False, "returncode": 1, "stdout": BIG, "stderr": "boom"},
        "thought": "run the tests",
        "iteration": i,
    }


def context_with(steps):
    return {"bug_report": "the bug", "history": steps, "system": ""}


def test_short_history_is_unchanged():
    context = context_with([read_step(i) for i in range(FULL_STEPS)])
    assert compact_history(context) is context


def test_older_steps_lose_bulky_fields_and_recent_steps_keep_them():
    steps = [read_step(i) for i in range(FULL_STEPS + 3)]
    compacted = compact_history(context_with(steps))["history"]

    assert len(compacted) == len(steps)
    for step in compacted[:3]:
        assert "content" not in step["result"]
        # What was done and how it went are kept
        assert step["action"]["args"]["path"].startswith("file")
        assert step["result"]["success"] is True
        assert step["result"]["total"] == 5000
    for step in compacted[3:]:
        assert step["result"]["content"] == BIG


def test_the_agent_history_itself_is_not_changed():
    steps = [exec_step(i) for i in range(FULL_STEPS + 2)]
    context = context_with(steps)
    compact_history(context)
    assert all(step["result"]["stdout"] == BIG for step in context["history"])


def test_long_arguments_of_older_steps_are_shortened():
    step = {
        "action": {"tool": "write_file", "args": {"path": "big.py", "content": BIG}},
        "result": {"success": True, "path": "big.py"},
        "thought": "write it",
        "iteration": 1,
    }
    compacted = compact_history(context_with([step] * (FULL_STEPS + 1)))["history"][0]
    assert compacted["action"]["args"]["path"] == "big.py"
    assert compacted["action"]["args"]["content"] == f"[{len(BIG)} characters, not shown]"


def test_long_errors_of_older_steps_are_cut():
    step = {"action": {"tool": "exec", "args": {"command": "make"}},
            "result": {"success": False, "error": "e" * 5000}, "thought": "", "iteration": 1}
    compacted = compact_history(context_with([step] * (FULL_STEPS + 1)))["history"][0]
    assert len(compacted["result"]["error"]) < 400


def test_message_size_stops_growing_with_the_number_of_steps():
    client = LLMClient("key")
    sizes = []
    for count in (20, 40):
        steps = [read_step(i) if i % 2 else exec_step(i) for i in range(count)]
        sizes.append(len(client._build_user_message(compact_history(context_with(steps)))))
    # 20 more steps add only their one-line summaries, not 20 more file contents
    assert sizes[1] - sizes[0] < 20 * 500


def test_chat_sends_the_compacted_history(monkeypatch):
    sent = {}

    class Reply:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "thought: ok\naction: \ndone: true\nsummary: ok"}]}

    def fake_post(url, headers, json, timeout):
        sent["content"] = json["messages"][0]["content"]
        return Reply()

    monkeypatch.setattr("main.requests.post", fake_post)
    steps = [read_step(i) for i in range(FULL_STEPS + 10)]
    LLMClient("key").chat(context_with(steps))
    # Only the last FULL_STEPS file contents are in the request
    # (each one is cut to 2000 characters, about 333 lines of "x = 1")
    assert 0 < sent["content"].count("x = 1") <= FULL_STEPS * 400
    assert sent["content"].count("read file") == len(steps)
