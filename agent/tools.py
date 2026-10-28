"""
Debug Agent tools
"""

import os
import re
import signal
import subprocess
import fnmatch
from typing import Dict, Callable, List
from functools import wraps
from .tool_system import tool_system

# Imported lazily to avoid a circular import
def _get_test_tools():
    from . import test_tools
    return test_tools


def project_dirs() -> List[str]:
    """Folders the file tools may change: the one CookieRookie was started in"""
    return [os.getcwd()]


def is_inside_project(path: str) -> bool:
    """True if path is inside one of project_dirs(), after resolving .. and symlinks"""
    target = os.path.realpath(path)
    for folder in project_dirs():
        folder = os.path.realpath(folder)
        try:
            if os.path.commonpath([folder, target]) == folder:
                return True
        except ValueError:  # different drives on Windows
            continue
    return False


def inside_project_only(tool: Callable) -> Callable:
    """Make a file-changing tool refuse paths outside the project. Without this, a confused model
    (or instructions planted in a file it reads) could change ~/.bashrc or ~/.ssh/authorized_keys."""
    @wraps(tool)
    def guarded(*args, **kwargs):
        path = args[0] if args else kwargs.get("path")
        # A missing path is left to the tool, so the model gets the tool's own argument error
        if path is not None and not is_inside_project(str(path)):
            return {"success": False,
                    "error": f"{path} is outside the project folder ({os.getcwd()}). "
                             "Only files inside it can be changed; use a path inside the project."}
        return tool(*args, **kwargs)
    return guarded


def reads_outside_project(arg: str, default: str = ".") -> Callable[[dict], bool]:
    """asks_when for a tool that reads the file or folder in argument arg: True when that is
    outside the project. Reading runs without asking, but what is read is sent to the API, so a
    confused model (or instructions planted in a file it reads) could send ~/.ssh/id_rsa or
    ~/.aws/credentials there without the user ever seeing it."""
    def outside(args: dict) -> bool:
        path = args.get(arg)
        return not is_inside_project(str(default if path is None else path))
    return outside


# ========== Tool implementations ==========

def read_file(path: str, offset: int = 1, limit: int = 100) -> dict:
    """Read a file by line numbers
    
    Args:
        path: file path
        offset: first line to read (1-indexed)
        limit: maximum number of lines
    """
    try:
        offset, limit = int(offset), int(limit)
        # Below 1, lines[offset - 1:] would count from the end of the file
        if offset < 1 or limit < 1:
            return {"success": False, "error": f"offset and limit must be at least 1 (got offset={offset}, limit={limit})"}
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        end = min(offset + limit - 1, total_lines)

        # An empty file (an __init__.py, a new module) used to fail with "Offset 1 beyond file
        # length 0", and the model went on as if the file could not be read
        if total_lines == 0 and offset == 1:
            return {"success": True, "content": "", "lines": "0-0", "total": 0,
                    "message": "The file is empty"}

        if offset > total_lines:
            return {"success": False, "error": f"Offset {offset} beyond file length {total_lines}"}
        
        content = "".join(lines[offset-1:end])
        
        return {
            "success": True,
            "content": content,
            "lines": f"{offset}-{end}",
            "total": total_lines
        }
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@inside_project_only
def edit_file(path: str, line: int = None, new_string: str = None,
              old_string: str = None) -> dict:
    """Edit a file
    
    Args:
        path: file path
        line: line number (preferred)
        new_string: the new content
        old_string: the old content (fallback when there is no line)
    """
    if new_string is None:
        return {"success": False, "error": "new_string is missing: give the new content"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        edit_mode = None

        if line is not None:
            # Replace a line by its number
            line = int(line)
            if line < 1 or line > len(lines):
                return {"success": False, "error": f"Line {line} out of range (1-{len(lines)})"}
            # Original implementation, kept for comparison while learning
            # lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
            lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
            edit_mode = "line"
        elif old_string is not None:
            # Replace a string
            content = "".join(lines)
            if old_string not in content:
                return {"success": False, "error": "old_string not found in file"}
            # Replacing the first of several matches may change the wrong place
            occurrences = content.count(old_string)
            if occurrences > 1:
                return {"success": False,
                        "error": f"old_string appears {occurrences} times in the file; include more surrounding "
                                 "lines so it matches once, or edit by line number"}
            # Original implementation, kept for comparison while learning
            # content = content.replace(old_string, new_string, 1)
            content = content.replace(old_string, new_string, 1)
            lines = content.splitlines(keepends=True)
            edit_mode = "old_string"
        else:
            return {"success": False, "error": "Must provide either line or old_string"}
        
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Original return value (kept for comparison while learning)
        # return {"success": True, "message": f"File edited (line {line})"}

        # New return value: expose the key details to the context above
        preview_new = None
        if line is not None and 1 <= line <= len(lines):
            # Preview without the line break
            preview_new = lines[line - 1].rstrip("\n")

        return {
            "success": True,
            "message": f"File edited ({edit_mode})",
            "path": path,
            "line": line,
            "mode": edit_mode,
            "new_line": preview_new,
        }
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Stop a command started by exec and every process it started (e.g. `server & sleep 99`)."""
    if hasattr(os, "killpg"):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    proc.kill()


def exec(command: str, workdir: str = None, timeout: int = 30) -> dict:
    """Run a shell command

    Args:
        command: the command to run
        workdir: working directory
        timeout: timeout in seconds
    """
    try:
        # stdin is closed: a command that asks for input (input(), a y/n prompt) gets end-of-file
        # and fails at once, instead of waiting on the user's keyboard until the timeout.
        # Its own session lets a timeout stop everything it started, not just the shell.
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workdir,
            start_new_session=True
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            stdout, stderr = proc.communicate()
            # Keep what it printed before the timeout: it shows where the command got stuck
            error = f"Command timeout after {timeout}s (stopped)"
            printed = ((stdout or "") + (stderr or "")).strip()
            if printed:
                error += f". Last output:\n{printed[-500:]}"
            return {
                "success": False,
                "error": error,
                "stdout": stdout,
                "stderr": stderr
            }

        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# Folders that hold installed packages, caches or version control data, not the project's code.
# They can hold thousands of files, which pushed the project's own files out of the first 50 results.
SKIP_DIRS = {"node_modules", "venv", "env", "__pycache__", "site-packages", "dist", "build"}


def _walk_project(path: str):
    """Like os.walk, in a stable order, without SKIP_DIRS and hidden folders (.git, .venv, ...).
    Only folders found during the walk are skipped, so path itself may be one of them."""
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        yield root, sorted(files)


def search_files(pattern: str, path: str = ".", file_glob: str = "*.py", use_regex: bool = False) -> dict:
    """Search file contents for pattern

    Args:
        pattern: Text to look for (a regex if use_regex is True)
        path: Folder to search (installed packages, caches and hidden folders are skipped)
        file_glob: Which files to search, e.g. "*.py", or "src/*.py" to match the path
    """
    try:
        matches = []
        # A plain pattern is matched as text, so characters like ( or * need no escaping
        regex = re.compile(pattern) if use_regex else None

        for root, files in _walk_project(path):
            for filename in files:
                filepath = os.path.join(root, filename)
                target = os.path.relpath(filepath, path).replace("\\", "/") if "/" in file_glob else filename
                if not fnmatch.fnmatch(target, file_glob):
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            text = line.rstrip("\n")
                            if (regex.search(text) if use_regex else pattern in text):
                                matches.append({"file": filepath, "line": i, "content": text.strip()})
                except (OSError, UnicodeDecodeError):
                    continue

        return {
            "success": True,
            "matches": matches[:50],  # at most 50, so the reply stays short
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@inside_project_only
def write_file(path: str, content: str) -> dict:
    """Write content to a file (created if missing, replaced if it exists)

    Args:
        path: file path
        content: file content
    """
    try:
        # A new file may go in a folder that does not exist yet (e.g. tests/)
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "message": f"File written: {path}",
            "path": path
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_files(pattern: str, path: str = ".", use_regex: bool = False) -> dict:
    """Find files by name

    Args:
        pattern: File name pattern like "*.py" ("src/*.py" matches the path; a regex if use_regex)
        path: Folder to search (installed packages, caches and hidden folders are skipped)
    """
    try:
        matches: List[str] = []

        for root, files in _walk_project(path):
            for filename in files:
                filepath = os.path.join(root, filename)
                if use_regex:
                    found = re.search(pattern, filename)
                elif "/" in pattern or "\\" in pattern:
                    found = fnmatch.fnmatch(os.path.relpath(filepath, path).replace("\\", "/"), pattern)
                else:
                    found = fnmatch.fnmatch(filename, pattern)
                if found:
                    matches.append(filepath)

        return {
            "success": True,
            "matches": matches[:50],
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== Tool registration ==========

def register_base_tools() -> None:
    """Register the base tools in ToolSystem"""
    # The descriptions go to the model with each tool (in the prompt and in the API's tool list).
    # The tools that read run without asking inside the project, and ask first outside it
    outside_note = "; asks the user first for a path outside the project folder"
    tool_system.register("read_file", read_file, confirmable=False,
                        description="Read lines of a file (offset: first line, from 1; limit: how many lines)"
                                    + outside_note,
                        asks_when=reads_outside_project("path"))
    tool_system.register("edit_file", edit_file, confirmable=True,
                        description="Change a file: replace line number line with new_string (preferred), "
                                    "or replace old_string, which must appear exactly once, with new_string")
    tool_system.register("write_file", write_file, confirmable=True,
                        description="Create a file, or replace everything in it, with content")
    tool_system.register("exec", exec, confirmable=True,
                        description="Run a shell command (in workdir, default: the project folder); "
                                    "it is stopped after timeout seconds")
    tool_system.register("search_files", search_files, confirmable=False,
                        description="Search the contents of files matching file_glob under path for pattern "
                                    "(plain text, or a regex with use_regex=True)" + outside_note,
                        asks_when=reads_outside_project("path"))
    tool_system.register("find_files", find_files, confirmable=False,
                        description="Find files under path whose name matches pattern "
                                    "(a glob like *.py, or a regex with use_regex=True)" + outside_note,
                        asks_when=reads_outside_project("path"))

    # Test tools
    tt = _get_test_tools()
    # Running the tests runs the project's code (test files, conftest.py, package.json scripts),
    # so like exec it waits for the user
    tool_system.register("test_run", tt.test_run, confirmable=True,
                        description="Run tests (path=project directory, pattern=test file, directory or glob; default: every test the framework finds, framework=auto/pytest/unittest/jest/go)")
    tool_system.register("test_generate", tt.test_generate, confirmable=False,
                        description="Read a source file to prepare writing tests for it" + outside_note,
                        asks_when=reads_outside_project("source", default=""))


def register_tools() -> Dict[str, Callable]:
    """Register all available tools"""
    register_base_tools()
    # The registered versions, which report wrong arguments back to the model instead of raising
    names = ["read_file", "edit_file", "write_file", "exec", "search_files", "find_files"]
    return {name: tool_system.get(name).fn for name in names}
