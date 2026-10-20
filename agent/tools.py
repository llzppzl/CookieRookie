"""
Debug Agent 工具集
"""

import os
import re
import signal
import subprocess
import fnmatch
from typing import Dict, Callable, List
from functools import wraps
from .tool_system import tool_system

# 延迟导入避免循环依赖
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


# ========== 工具实现 ==========

def read_file(path: str, offset: int = 1, limit: int = 100) -> dict:
    """读取文件内容 (按行号)
    
    Args:
        path: 文件路径
        offset: 起始行号 (1-indexed)
        limit: 最大行数
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
    """编辑文件
    
    Args:
        path: 文件路径
        line: 行号 (优先使用)
        new_string: 新内容
        old_string: 旧内容 (备用)
    """
    if new_string is None:
        return {"success": False, "error": "new_string is missing: give the new content"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        edit_mode = None

        if line is not None:
            # 按行号修改
            line = int(line)
            if line < 1 or line > len(lines):
                return {"success": False, "error": f"Line {line} out of range (1-{len(lines)})"}
            # 保留原始实现，作为学习对比
            # lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
            lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
            edit_mode = "line"
        elif old_string is not None:
            # 字符串替换
            content = "".join(lines)
            if old_string not in content:
                return {"success": False, "error": "old_string not found in file"}
            # Replacing the first of several matches may change the wrong place
            occurrences = content.count(old_string)
            if occurrences > 1:
                return {"success": False,
                        "error": f"old_string appears {occurrences} times in the file; include more surrounding "
                                 "lines so it matches once, or edit by line number"}
            # 保留原始实现，作为学习对比
            # content = content.replace(old_string, new_string, 1)
            content = content.replace(old_string, new_string, 1)
            lines = content.splitlines(keepends=True)
            edit_mode = "old_string"
        else:
            return {"success": False, "error": "Must provide either line or old_string"}
        
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # 原始返回值（保留方便对比学习）
        # return {"success": True, "message": f"File edited (line {line})"}

        # 新的返回信息：尽量把关键信息暴露给上层 context
        preview_new = None
        if line is not None and 1 <= line <= len(lines):
            # 去掉换行后的预览
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
    """执行 shell 命令
    
    Args:
        command: 要执行的命令
        workdir: 工作目录
        timeout: 超时秒数
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
    """写入文件内容

    Args:
        path: 文件路径
        content: 文件内容
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


# ========== 工具注册 ==========

def register_base_tools() -> None:
    """注册基础工具到 ToolSystem"""
    tool_system.register("read_file", read_file, confirmable=False)
    tool_system.register("edit_file", edit_file, confirmable=True)
    tool_system.register("write_file", write_file, confirmable=True)
    tool_system.register("exec", exec, confirmable=True)
    tool_system.register("search_files", search_files, confirmable=False)
    tool_system.register("find_files", find_files, confirmable=False)

    # 测试工具
    tt = _get_test_tools()
    tool_system.register("test_run", tt.test_run, confirmable=False,
                        description="Run tests (path=project directory, pattern=test file, directory or glob; default: every test the framework finds, framework=auto/pytest/unittest/jest/go)")
    tool_system.register("test_generate", tt.test_generate, confirmable=False,
                        description="分析源码，准备生成测试")


def register_tools() -> Dict[str, Callable]:
    """注册所有可用工具"""
    register_base_tools()
    # The registered versions, which report wrong arguments back to the model instead of raising
    names = ["read_file", "edit_file", "write_file", "exec", "search_files", "find_files"]
    return {name: tool_system.get(name).fn for name in names}
