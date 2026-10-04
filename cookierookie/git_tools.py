"""Git operation tools for CookieRookie agent."""

import subprocess
import os
from typing import Optional, List, Dict, Any


def git_status() -> Dict[str, Any]:
    """Get Git status.

    Returns:
        success: Whether the command succeeded
        files: List of changed files
        count: Number of changed files
        clean: Whether the working tree is clean
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
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
        cmd = ["git", "diff"]
        if path:
            cmd.append(path)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
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
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # First git add
        if files:
            add_cmd = ["git", "add"] + files
        else:
            add_cmd = ["git", "add", "."]

        add_result = subprocess.run(
            add_cmd,
            capture_output=True,
            text=True,
            cwd=repo_dir
        )

        if add_result.returncode != 0:
            return {
                "success": False,
                "message": "git add failed",
                "output": add_result.stdout,
                "error": add_result.stderr
            }

        # Then git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=repo_dir
        )

        return {
            "success": commit_result.returncode == 0,
            "message": message,
            "output": commit_result.stdout,
            "error": commit_result.stderr if commit_result.returncode != 0 else ""
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
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Get current branch
        current_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=repo_dir
        )
        current = current_result.stdout.strip()

        branches = []
        if list_branches:
            result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True,
                cwd=repo_dir
            )
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
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
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%H|%s|%an|%ad|%ai"],
            capture_output=True,
            text=True,
            cwd=repo_dir
        )

        commits = []
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for line in lines:
            if line:
                parts = line.split("|")
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
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = ["git", "checkout"]
        if create:
            cmd.extend(["-b", branch])
        else:
            cmd.append(branch)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_dir
        )

        return {
            "success": result.returncode == 0,
            "branch": branch,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else ""
        }
    except Exception as e:
        return {
            "success": False,
            "branch": branch,
            "output": "",
            "error": str(e)
        }
