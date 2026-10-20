"""agent/test_cli_loop.py - quitting and stopping in interactive mode"""
import builtins

import pytest

import main


class FakeAgent:
    """Stands in for InteractiveAgent; run() can be told to raise KeyboardInterrupt (Ctrl+C)"""
    pending_action = None
    current_plan = None

    def __init__(self, interrupt_on=None):
        self.interrupt_on = interrupt_on
        self.tasks = []

    def run(self, task):
        self.tasks.append(task)
        if task == self.interrupt_on:
            raise KeyboardInterrupt
        return f"done: {task}"


def start(monkeypatch, inputs, agent):
    """Run interactive_main with scripted input; an item that is an exception is raised by input()"""
    script = iter(inputs)

    def fake_input(prompt=""):
        try:
            item = next(script)
        except StopIteration:
            pytest.fail("interactive mode asked for input again instead of quitting")
        if isinstance(item, BaseException):
            raise item
        return item

    # Only the loop is under test: no real config, client or agent
    monkeypatch.setattr(main, "load_config", lambda *a, **k: {"api_key": "k", "model": "m", "base_url": "u",
                                                               "max_tokens": 100})
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: object())
    monkeypatch.setattr("agent.core.create_interactive_agent", lambda *a, **k: agent)
    monkeypatch.setattr(builtins, "input", fake_input)
    main.interactive_main()


def test_end_of_input_quits(monkeypatch):
    # Before: EOFError was caught as an error, so it printed "Error: " and asked again forever
    start(monkeypatch, [EOFError()], FakeAgent())


def test_ctrl_c_at_the_prompt_quits(monkeypatch):
    start(monkeypatch, [KeyboardInterrupt()], FakeAgent())


def test_ctrl_c_during_a_task_stops_only_that_task(monkeypatch, capsys):
    agent = FakeAgent(interrupt_on="long task")
    start(monkeypatch, ["long task", "next task", "exit"], agent)

    assert agent.tasks == ["long task", "next task"]
    out = capsys.readouterr().out
    assert "Stopped the current task" in out
    assert "done: next task" in out
