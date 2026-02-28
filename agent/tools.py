"""
Debug Agent 工具集
"""

import os
import re
import subprocess
import glob
from typing import Dict, Callable


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
        
        if line is not None:
            # 按行号修改
            if line < 1 or line > len(lines):
                return {"success": False, "error": f"Line {line} out of range (1-{len(lines)})"}
            lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
        elif old_string is not None:
            # 字符串替换
            content = "".join(lines)
            if old_string not in content:
                return {"success": False, "error": "old_string not found in file"}
            content = content.replace(old_string, new_string, 1)
            lines = content.splitlines(keepends=True)
        else:
            return {"success": False, "error": "Must provide either line or old_string"}
        
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        return {"success": True, "message": f"File edited (line {line})"}
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


def search_files(pattern: str, path: str = ".", file_glob: str = "*.py") -> dict:
    """搜索文件中的关键词
    
    Args:
        pattern: 搜索模式 (正则)
        path: 搜索路径
        file_glob: 文件匹配模式
    """
    try:
        matches = []
        glob_pattern = os.path.join(path, "**", file_glob)
        
        for filepath in glob.glob(glob_pattern, recursive=True):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(pattern, line):
                            matches.append({
                                "file": filepath,
                                "line": i,
                                "content": line.strip()
                            })
            except:
                continue
        
        return {
            "success": True,
            "matches": matches[:50],  # 限制返回数量
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_files(pattern: str, path: str = ".") -> dict:
    """查找文件
    
    Args:
        pattern: 文件名匹配模式
        path: 搜索路径
    """
    try:
        matches = []
        for root, dirs, files in os.walk(path):
            for filename in files:
                if re.search(pattern, filename):
                    matches.append(os.path.join(root, filename))
        
        return {
            "success": True,
            "matches": matches[:50],
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== 工具注册 ==========

def register_tools() -> Dict[str, Callable]:
    """注册所有可用工具"""
    return {
        "read_file": read_file,
        "edit_file": edit_file,
        "exec": exec,
        "search_files": search_files,
        "find_files": find_files,
    }
