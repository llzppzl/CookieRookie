"""agent/test_git_history.py - the model reads git_diff, git_status and git_log results as text

They used to go through the 800-character JSON view of other tools: a diff arrived with every
line break as \\n and was cut off after a few dozen lines without saying so, and ten commits
of git_log did not fit either.
"""
import subprocess

import main
from agent.git_tools import git_diff, git_log, git_status, git_commit
from agent.history import FULL_STEPS, compact_history


def history_text(*steps):
    context = {"task": "task", "history": [
        {"action": {"tool": tool, "args": args}, "result": result, "thought": "t", "iteration": i}
        for i, (tool, args, result) in enumerate(steps, 1)]}
    return main.LLMClient("key")._build_user_message(compact_history(context))


def repo(tmp_path, monkeypatch):
    for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "test@example.com"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_whole_diff_is_shown_as_text(tmp_path, monkeypatch):
    path = repo(tmp_path, monkeypatch)
    (path / "app.py").write_text("".join(f"value_{i} = {i}\n" for i in range(60)))
    git_commit("Add app.py")
    (path / "app.py").write_text("".join(f"value_{i} = {i * 2}\n" for i in range(60)))

    text = history_text(("git_diff", {}, git_diff()))
    assert "```diff" in text
    assert "+value_59 = 118" in text  # the last line, past the 800 characters shown before
    assert "\\n" not in text
    assert "[cut off" not in text


def test_a_long_diff_says_it_was_cut_off():
    diff = "".join(f"+line {i}\n" for i in range(2000))
    text = history_text(("git_diff", {}, {"success": True, "diff": diff, "returncode": 0, "stderr": ""}))
    assert len(text) < main.MAX_DIFF_CHARS + 500
    assert "cut off: call git_diff with path=" in text


def test_an_empty_diff_says_what_it_does_not_show():
    text = history_text(("git_diff", {"path": "a.py"}, {"success": True, "diff": "", "returncode": 0, "stderr": ""}))
    assert "no uncommitted changes in a.py" in text
    assert "staged or untracked" in text


def test_an_older_diff_is_left_out_but_not_reported_as_empty():
    diff_step = ("git_diff", {}, {"success": True, "diff": "+x = 1\n", "returncode": 0, "stderr": ""})
    later = ("git_status", {}, {"success": True, "files": [], "count": 0, "clean": True})
    text = history_text(diff_step, *[later] * FULL_STEPS)
    assert "+x = 1" not in text
    assert "no uncommitted changes" not in text
    assert "call git_diff again" in text


def test_status_and_log_are_listed(tmp_path, monkeypatch):
    path = repo(tmp_path, monkeypatch)
    for i in range(10):
        (path / f"f{i}.py").write_text("")
        git_commit(f"Add module number {i} with a fairly long subject line")
    (path / "new.py").write_text("")

    text = history_text(("git_status", {}, git_status()), ("git_log", {}, git_log()))
    assert "1 changed files:\n  - new.py" in text
    assert "10 commits, newest first" in text
    # Before, the JSON view cut this list off after a few commits
    assert "Add module number 0 with a fairly long subject line (Test)" in text
    assert "Result(raw)" not in text
