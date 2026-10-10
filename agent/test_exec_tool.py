"""Tests for the exec tool: no terminal input, and timeouts that really stop the command."""
import os
import subprocess
import sys
import time

import pytest

from agent.tools import exec as run_command

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
posix_only = pytest.mark.skipif(os.name != "posix", reason="needs a POSIX shell and pty")


def test_returns_output_and_exit_code():
    result = run_command(f'"{sys.executable}" -c "print(42)"')
    assert result["success"] is True
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "42"


def test_failing_command_is_not_success():
    result = run_command(f'"{sys.executable}" -c "import sys; sys.exit(3)"')
    assert result["success"] is False
    assert result["returncode"] == 3


@posix_only
def test_command_asking_for_input_does_not_wait_on_the_terminal():
    """Run exec the way a user does, with a terminal as stdin: input() must fail at once."""
    import pty

    child = (
        "import sys, time; sys.path.insert(0, %r); from agent.tools import exec as run;"
        "t = time.time(); r = run(%r, timeout=20); print(round(time.time() - t, 1), r['success'])"
        % (REPO, f'"{sys.executable}" -c "input()"')
    )
    master, slave = pty.openpty()
    try:
        out = subprocess.run([sys.executable, "-c", child], stdin=slave,
                             capture_output=True, text=True, timeout=60).stdout.split()
    finally:
        os.close(master)
        os.close(slave)
    elapsed, success = float(out[0]), out[1]
    assert success == "False"  # input() got end-of-file
    assert elapsed < 10  # instead of waiting 20s for the keyboard


@posix_only
def test_timeout_keeps_what_was_printed():
    start = time.time()
    result = run_command("echo started; sleep 30", timeout=1)
    assert time.time() - start < 10
    assert result["success"] is False
    assert "timeout after 1s" in result["error"]
    assert "started" in result["error"]
    assert "started" in result["stdout"]


@posix_only
def test_timeout_stops_processes_the_command_started():
    result = run_command("sleep 30 & echo $!; wait", timeout=1)
    assert result["success"] is False
    pid = int(result["stdout"].split()[0])
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"background process {pid} is still running after the timeout")
