"""agent/test_pending_answer.py - what typing does while an edit or command waits for approval"""
import builtins

import pytest

import main


WRITE_A = {"thought": "write a", "action": {"tool": "write_file", "args": {"path": "a.txt", "content": "A"}},
           "done": False, "raw": "write a"}


def done(summary):
    return {"thought": "", "action": {}, "done": True, "summary": summary, "raw": summary}


class FakeLLM:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(context)
        return next(self.replies)


def start(monkeypatch, tmp_path, inputs, replies):
    """Run interactive mode in tmp_path with scripted input and model replies"""
    monkeypatch.chdir(tmp_path)
    llm = FakeLLM(replies)
    script = iter(inputs)

    def fake_input(prompt=""):
        try:
            return next(script)
        except StopIteration:
            pytest.fail("interactive mode asked for more input than the test gave")

    monkeypatch.setattr(main, "load_config", lambda *a, **k: {"api_key": "k", "model": "m", "base_url": "u",
                                                               "max_tokens": 100})
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: llm)
    monkeypatch.setattr(builtins, "input", fake_input)
    main.interactive_main()
    return llm


def test_text_typed_while_an_action_waits_is_not_a_new_task(monkeypatch, tmp_path):
    # Before: "task B" started a new task and left task A's write waiting, so /confirm wrote a.txt
    llm = start(monkeypatch, tmp_path, ["task A", "use b.txt instead", "/confirm", "exit"],
                [WRITE_A, done("task A done another way")])

    assert not (tmp_path / "a.txt").exists()
    # The model went on with task A and read why the write was skipped
    resumed = llm.contexts[-1]
    assert resumed["task"] == "task A"
    assert "use b.txt instead" in resumed["history"][-1]["result"]["error"]


def test_y_runs_the_waiting_action(monkeypatch, tmp_path):
    start(monkeypatch, tmp_path, ["task A", "y", "exit"], [WRITE_A, done("written")])

    assert (tmp_path / "a.txt").read_text() == "A"


def test_n_skips_the_waiting_action(monkeypatch, tmp_path, capsys):
    start(monkeypatch, tmp_path, ["task A", "N", "/confirm", "exit"], [WRITE_A])

    assert not (tmp_path / "a.txt").exists()
    assert "Nothing to confirm" in capsys.readouterr().out


def test_a_task_with_nothing_waiting_still_runs(monkeypatch, tmp_path, capsys):
    start(monkeypatch, tmp_path, ["task B", "exit"], [done("task B done")])

    assert "task B done" in capsys.readouterr().out
