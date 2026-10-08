"""agent/test_git_tools.py"""
import pytest
import os
import tempfile
import subprocess
from agent.git_tools import git_status, git_diff, git_log


class TestGitTools:
    def test_git_status(self):
        result = git_status()
        assert "success" in result
        assert "files" in result
        assert "count" in result
        assert "clean" in result

    def test_git_log(self):
        result = git_log(limit=5)
        assert "success" in result or "error" in result

    def test_git_diff(self):
        result = git_diff()
        assert "success" in result
        assert "diff" in result


# ---------- in the user's project ----------

from agent.git_tools import git_checkout, git_commit, register_git_tools
from agent.tool_system import tool_system


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty git repository as the current directory, like a project CookieRookie was started in"""
    for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "test@example.com"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    # The tests commit with "git add .". If the tools ran git in another directory, they would
    # commit there: the old code, run with these tests, committed in the CookieRookie checkout
    (tmp_path / "probe").write_text("")
    assert git_status()["files"] == ["probe"], "the git tools must run git in the current directory"
    (tmp_path / "probe").unlink()
    return tmp_path


def test_git_tools_work_on_the_current_directory(repo):
    (repo / "app.py").write_text("x = 1\n")
    assert git_status()["files"] == ["app.py"]

    assert git_commit("Add app.py")["success"] is True

    assert git_log()["commits"][0]["subject"] == "Add app.py"
    assert git_status()["clean"] is True


def test_git_status_keeps_the_whole_file_name(repo):
    (repo / "README.md").write_text("a\n")
    git_commit("Add README")
    (repo / "README.md").write_text("b\n")

    # git status --porcelain prints " M README.md"; stripping the output used to give "EADME.md"
    assert git_status()["files"] == ["README.md"]


def test_git_tools_say_when_there_is_no_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.chdir(tmp_path)

    for result in (git_status(), git_log()):
        assert result["success"] is False
        assert "not a git repository" in result["error"]


def test_git_log_reads_a_subject_with_a_bar(repo):
    (repo / "a.py").write_text("")
    git_commit("Use a | b")

    assert git_log()["commits"][0]["subject"] == "Use a | b"


def test_a_commit_says_why_it_failed(repo):
    result = git_commit("Nothing")

    assert result["success"] is False
    assert "nothing to commit" in result["error"]


def test_git_commit_takes_one_file_as_a_string(repo):
    (repo / "a.py").write_text("")
    (repo / "b.py").write_text("")

    assert git_commit("Add a.py", files="a.py")["success"] is True
    assert git_status()["files"] == ["b.py"]


def test_a_path_or_branch_is_not_read_as_an_option(repo):
    (repo / "a.py").write_text("")
    git_commit("Add a.py")

    leak = repo / "leak.txt"

    # An absolute path, so the file is found wherever git runs
    git_diff(f"--output={leak}")
    assert not leak.exists()
    # git checkout --detach would succeed if it were read as an option
    assert git_checkout("--detach")["success"] is False


def test_git_tools_are_offered_and_commits_ask_first():
    register_git_tools()

    tools = tool_system.list_tools()
    for name in ("git_status", "git_diff", "git_log", "git_branch", "git_commit", "git_checkout"):
        assert name in tools
        assert tools[name].description
    assert tool_system.is_confirmable("git_commit")
    assert tool_system.is_confirmable("git_checkout")
    assert not any(tool_system.is_confirmable(name) for name in ("git_status", "git_diff", "git_log", "git_branch"))
