"""
Debug Agent 工具集
"""

import os
import re
import subprocess
import glob
import fnmatch
from typing import Dict, Callable, List
from .tool_system import tool_system

# 延迟导入避免循环依赖
def _get_test_tools():
    from . import test_tools
    return test_tools


# ========== 工具实现 ==========

def read_file(path: str, offset: int = 1, limit: int = 100) -> dict:
    """读取文件内容 (按行号)
    
    Args:
        path: 文件路径
        offset: 起始行号 (1-indexed)
        limit: 最大行数
    """
    try:
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


def edit_file(path: str, line: int = None, new_string: str = None,
              old_string: str = None) -> dict:
    """编辑文件
    
    Args:
        path: 文件路径
        line: 行号 (优先使用)
        new_string: 新内容
        old_string: 旧内容 (备用)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        edit_mode = None

        if line is not None:
            # 按行号修改
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


def exec(command: str, workdir: str = None, timeout: int = 30) -> dict:
    """执行 shell 命令
    
    Args:
        command: 要执行的命令
        workdir: 工作目录
        timeout: 超时秒数
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir
        )
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timeout after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(pattern: str, path: str = ".", file_glob: str = "*.py", use_regex: bool = False) -> dict:
    """搜索文件中的关键词
    
    Args:
        pattern: 搜索模式 (正则)
        path: 搜索路径
        file_glob: 文件匹配模式
    """
    try:
        matches = []
        glob_pattern = os.path.join(path, "**", file_glob)

        # 如果使用正则，则按照原来的行为处理；否则按字面/通配符匹配
        regex = re.compile(pattern) if use_regex else None

        for filepath in glob.glob(glob_pattern, recursive=True):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        text = line.rstrip("\n")
                        matched = False
                        if use_regex:
                            if regex.search(text):
                                matched = True
                        else:
                            # 简单字面包含匹配，避免正则陷阱
                            if pattern in text:
                                matched = True

                        if matched:
                            matches.append(
                                {
                                    "file": filepath,
                                    "line": i,
                                    "content": text.strip(),
                                }
                            )
            except:
                continue
        
        return {
            "success": True,
            "matches": matches[:50],  # 限制返回数量
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str) -> dict:
    """写入文件内容

    Args:
        path: 文件路径
        content: 文件内容
    """
    try:
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
    """查找文件

    Args:
        pattern: 文件名匹配模式
        path: 搜索路径
    """
    try:
        matches: List[str] = []

        # 原始实现（保留作为对比学习）：
        # for root, dirs, files in os.walk(path):
        #     for filename in files:
        #         if re.search(pattern, filename):
        #             matches.append(os.path.join(root, filename))

        for root, dirs, files in os.walk(path):
            for filename in files:
                if use_regex:
                    # 显式使用正则时才按正则解释 pattern
                    if re.search(pattern, filename):
                        matches.append(os.path.join(root, filename))
                else:
                    # 默认使用通配/字面模式，避免正则错误（nothing to repeat 等）
                    rel_path = os.path.relpath(os.path.join(root, filename), path)
                    rel_path_norm = rel_path.replace("\\", "/")

                    # 如果 pattern 中带路径分隔符，则在相对路径上匹配；否则只匹配文件名
                    if "/" in pattern or "\\" in pattern:
                        if fnmatch.fnmatch(rel_path_norm, pattern):
                            matches.append(os.path.join(root, filename))
                    else:
                        if fnmatch.fnmatch(filename, pattern):
                            matches.append(os.path.join(root, filename))

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
                        description="执行测试 (path, pattern, framework)")
    tool_system.register("test_generate", tt.test_generate, confirmable=False,
                        description="分析源码，准备生成测试")


def register_tools() -> Dict[str, Callable]:
    """注册所有可用工具"""
    register_base_tools()
    return {
        "read_file": read_file,
        "edit_file": edit_file,
        "write_file": write_file,
        "exec": exec,
        "search_files": search_files,
        "find_files": find_files,
    }
