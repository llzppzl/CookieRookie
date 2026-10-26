"""agent/test_exec_history.py - the model sees what a failed command printed

A command that exits with an error (a failing test run, a script that raises) is the result the
model most needs to read. Before, the history showed only its stderr, so `pytest`, which prints
its failures to stdout, reached the model as " Result: failed - " and nothing else.
"""
import sys

import main
from agent.tools import exec as run_command


def history_text(tool, args, result):
    context = {"task": "task", "history": [{
        "action": {"tool": tool, "args": args},
        "result": result, "thought": "t", "iteration": 1}]}
    return main.LLMClient("key")._build_user_message(context)


def test_a_failed_command_shows_its_stdout_and_return_code():
    script = "print('test_divide failed: expected 2, got 3'); raise SystemExit(1)"
    result = run_command(f'"{sys.executable}" -c "{script}"')
    assert result["success"] is False
    text = history_text("exec", {"command": "pytest"}, result)
    assert "returncode=1" in text
    assert "test_divide failed: expected 2, got 3" in text


def test_a_failed_command_shows_stdout_and_stderr():
    result = {"success": False, "returncode": 2, "stdout": "collected 3 items", "stderr": "ImportError: no module x"}
    text = history_text("exec", {"command": "pytest"}, result)
    assert "collected 3 items" in text
    assert "ImportError: no module x" in text


def test_a_command_that_could_not_run_still_shows_the_error():
    # A timeout or a missing workdir has no return code, only an error
    result = {"success": False, "error": "Command timeout after 30s (stopped)"}
    text = history_text("exec", {"command": "sleep 99"}, result)
    assert "Result: failed - Command timeout after 30s (stopped)" in text
