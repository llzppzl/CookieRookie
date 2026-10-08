"""Git operation tools for CookieRookie agent.

They run git in the current directory: the project CookieRookie was started in.
"""

import subprocess
from typing import Optional, List, Dict, Any


def _git(*args: str) -> subprocess.CompletedProcess:
    """Run git in the current directory.

    These tools used to run git in the directory above this file: the CookieRookie checkout,
    or site-packages after pip install, so they never saw the user's project.
    """
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _error(result: subprocess.CompletedProcess) -> str:
    """Why a git command failed. Some reasons are on stdout, like "nothing to commit"."""
    return result.stderr.strip() or result.stdout.strip() or f"git exited with code {result.returncode}"


def git_status() -> Dict[str, Any]:
    """Get Git status.

    Returns:
        success: Whether the command succeeded
        files: List of changed files
        count: Number of changed files
        clean: Whether the working tree is clean
    """
    try:
        result = _git("status", "--porcelain")
        if result.returncode != 0:  # e.g. not a git repository
            return {"success": False, "files": [], "count": 0, "clean": False, "error": _error(result)}
        # Not strip(): the first line can start with a space (" M file" is a modified file),
        # and stripping it cut the first letter off the file name
        lines = result.stdout.splitlines()
        files = []
        for line in lines:
            if line:
                # Status format: XY filename, X=index status, Y=worktree status
                if len(line) > 3:
                    files.append(line[3:])
        return {
            "success": True,
            "files": files,
            "count": len(files),
            "clean": len(files) == 0
        }
    except Exception as e:
        return {
            "success": False,
            "files": [],
            "count": 0,
            "clean": True,
            "error": str(e)
        }


def git_diff(path: Optional[str] = None) -> Dict[str, Any]:
    """Get Git diff.

    Args:
        path: Optional path to get diff for

    Returns:
        success: Whether the command succeeded
        diff: The diff output
        returncode: The return code of the git command
    """
    try:
        # After "--", path can't be read as an option (git diff --output=FILE writes a file)
        result = _git("diff", "--", path) if path else _git("diff")
        return {
            "success": result.returncode == 0,
            "diff": result.stdout,
            "returncode": result.returncode,
            "stderr": result.stderr if result.returncode != 0 else ""
        }
    except Exception as e:
        return {
            "success": False,
            "diff": "",
            "returncode": -1,
            "error": str(e)
        }


def git_commit(message: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Commit changes.

    Args:
        message: Commit message
        files: Optional list of files to commit (default: all changes)

    Returns:
        success: Whether the command succeeded
        message: The commit message or error message
        output: Command output
        error: Error message if any
    """
    try:
        if isinstance(files, str):  # one file, not a list
            files = [files]
        # First git add
        add_result = _git("add", "--", *files) if files else _git("add", ".")

        if add_result.returncode != 0:
            return {
                "success": False,
                "message": "git add failed",
                "output": add_result.stdout,
                "error": add_result.stderr
            }

        # Then git commit
        commit_result = _git("commit", "-m", message)

        return {
            "success": commit_result.returncode == 0,
            "message": message,
            "output": commit_result.stdout,
            "error": _error(commit_result) if commit_result.returncode != 0 else ""
        }
    except Exception as e:
        return {
            "success": False,
            "message": message,
            "output": "",
            "error": str(e)
        }


def git_branch(list_branches: bool = False) -> Dict[str, Any]:
    """Branch operations.

    Args:
        list_branches: If True, return list of branches

    Returns:
        success: Whether the command succeeded
        branches: List of branches (if list_branches=True)
        current: Current branch name
    """
    try:
        # Get current branch
        current_result = _git("branch", "--show-current")
        if current_result.returncode != 0:
            return {"success": False, "branches": [], "current": "", "error": _error(current_result)}
        current = current_result.stdout.strip()

        branches = []
        if list_branches:
            result = _git("branch", "-a")
            lines = result.stdout.splitlines()
            for line in lines:
                # Remove * prefix for current branch
                branches.append(line.strip().lstrip("* ").strip())

        return {
            "success": True,
            "branches": branches,
            "current": current
        }
    except Exception as e:
        return {
            "success": False,
            "branches": [],
            "current": "",
            "error": str(e)
        }


def git_log(limit: int = 10) -> Dict[str, Any]:
    """Get Git log.

    Args:
        limit: Maximum number of commits to return

    Returns:
        success: Whether the command succeeded
        commits: List of commit info dictionaries
        count: Number of commits returned
    """
    try:
        # Fields are separated by \x1f rather than "|", which a commit subject can contain
        result = _git("log", f"--max-count={int(limit)}", "--pretty=format:%H%x1f%s%x1f%an%x1f%ad%x1f%ai")
        if result.returncode != 0:  # e.g. not a git repository, or no commits yet
            return {"success": False, "commits": [], "count": 0, "error": _error(result)}

        commits = []
        lines = result.stdout.splitlines()
        for line in lines:
            if line:
                parts = line.split("\x1f")
                if len(parts) >= 5:
                    commits.append({
                        "hash": parts[0],
                        "subject": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                        "datetime": parts[4]
                    })

        return {
            "success": True,
            "commits": commits,
            "count": len(commits)
        }
    except Exception as e:
        return {
            "success": False,
            "commits": [],
            "count": 0,
            "error": str(e)
        }


def git_checkout(branch: str, create: bool = False) -> Dict[str, Any]:
    """Switch branches.

    Args:
        branch: Branch name to switch to
        create: If True, create a new branch

    Returns:
        success: Whether the command succeeded
        branch: The branch name
        output: Command output
        error: Error message if any
    """
    try:
        if branch.startswith("-"):
            return {"success": False, "branch": branch, "output": "",
                    "error": f"Not a branch name: {branch}"}
        result = _git("checkout", "-b", branch) if create else _git("checkout", branch)

        return {
            "success": result.returncode == 0,
            "branch": branch,
            "output": result.stdout,
            "error": _error(result) if result.returncode != 0 else ""
        }
    except Exception as e:
        return {
            "success": False,
            "branch": branch,
            "output": "",
            "error": str(e)
        }


def register_git_tools() -> None:
    """Offer the git tools to the interactive agent. Committing and switching branches ask first."""
    from .tool_system import tool_system

    tool_system.register("git_status", git_status, confirmable=False,
                         description="List changed files in the project (git status)")
    tool_system.register("git_diff", git_diff, confirmable=False,
                         description="Show uncommitted changes, optionally for one path (path)")
    tool_system.register("git_log", git_log, confirmable=False,
                         description="Show recent commits (limit, default 10)")
    tool_system.register("git_branch", git_branch, confirmable=False,
                         description="Show the current branch; list_branches=True lists all branches")
    tool_system.register("git_commit", git_commit, confirmable=True,
                         description="Commit changes with a message (message); files: list of paths, default all changes")
    tool_system.register("git_checkout", git_checkout, confirmable=True,
                         description="Switch to a branch (branch); create=True creates it first")
