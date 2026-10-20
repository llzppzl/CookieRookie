"""agent/test_cli_options.py - --help and unknown options don't start a debug run"""
import os
import subprocess
import sys

import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args):
    return subprocess.run([sys.executable, os.path.join(REPO, "main.py"), *args], capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=60)


def test_help_prints_usage_and_runs_nothing():
    for flag in ("--help", "-h"):
        result = run_cli(flag)
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "Starting Debug Agent" not in result.stdout


def test_unknown_option_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(main, "main", lambda: (_ for _ in ()).throw(AssertionError("debug mode started")))
    assert main.cli(["--interactiv"]) == 2
    assert "Unknown option: --interactiv" in capsys.readouterr().out


def test_bug_reports_still_go_to_debug_mode(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "main", lambda: seen.append("debug"))
    monkeypatch.setattr(main, "interactive_main", lambda: seen.append("interactive"))

    assert main.cli(["calculator.py divides by zero"]) == 0
    assert main.cli(["-1 is returned for empty input"]) == 0  # starts with "-" but is a sentence
    assert main.cli(["--yes", "bug"]) == 0  # --yes is read by debug mode
    assert main.cli([]) == 0  # debug mode prints its own usage
    assert main.cli(["--interactive"]) == 0
    assert seen == ["debug", "debug", "debug", "debug", "interactive"]
