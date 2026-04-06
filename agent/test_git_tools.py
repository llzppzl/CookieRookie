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
