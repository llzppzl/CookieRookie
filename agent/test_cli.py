"""The `cookierookie` command (agent/cli.py) behaves like `python main.py`."""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_command(cwd, *args):
    env = {k: v for k, v in os.environ.items() if k != "DEBUG_BUG_REPORT"}
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run([sys.executable, "-c", "from agent.cli import main; main()", *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def test_command_without_arguments_prints_usage_from_any_folder(tmp_path):
    result = run_command(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Usage" in result.stdout


def test_command_runs_main_py_as_the_script(tmp_path, monkeypatch):
    import runpy
    from agent import cli
    calls = []
    monkeypatch.setattr(runpy, "run_module", lambda *a, **kw: calls.append((a, kw)))

    cli.main()

    assert calls == [(("main",), {"run_name": "__main__", "alter_sys": True})]


def test_pyproject_points_the_command_at_cli_main():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^cookierookie = "agent\.cli:main"$', text, re.M)
    # main.py is a top-level module, so the wheel must ship it next to the agent package
    assert re.search(r'^only-include = \["agent", "main\.py"\]$', text, re.M)
