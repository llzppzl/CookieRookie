# CookieRookie Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 CookieRookie 从 Debug Agent 打造成通用 Coding Agent，支持混合交互模式（自主执行+确认）、测试执行/生成、Git 集成

**Architecture:** 核心是 InteractiveAgent 类，负责任务规划、执行循环、确认机制。工具系统重构为插件化注册表（ToolSystem），支持 confirmable 标记。保持向后兼容，现有 DebugAgent 功能继续可用。

**Tech Stack:** Python 3, requests, subprocess (标准库)

---

## File Structure

```
agent/
├── __init__.py              # 导出 InteractiveAgent, ToolSystem
├── core.py                  # DebugAgent → InteractiveAgent (重构)
├── tools.py                 # 工具注册表 (重构，委托 ToolSystem)
├── tool_system.py           # 新增：插件化工具系统
├── git_tools.py             # 新增：Git 工具集
├── test_tools.py            # 新增：测试工具集
└── __pycache__/            # (自动生成)

docs/superpowers/plans/      # 本计划
docs/superpowers/specs/     # 设计文档

main.py                      # 保持不变
```

---

## Task 1: ToolSystem 插件化工具注册表

**Files:**
- Create: `agent/tool_system.py`
- Test: `agent/test_tool_system.py`

- [ ] **Step 1: 创建 tool_system.py 骨架**

```python
"""
ToolSystem - 插件化工具注册表
"""

from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    fn: Callable
    confirmable: bool = False
    description: str = ""
    args_schema: Optional[Dict[str, Any]] = None


class ToolSystem:
    """工具注册与管理"""

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        confirmable: bool = False,
        description: str = "",
        args_schema: Optional[Dict[str, Any]] = None
    ) -> None:
        """注册工具"""
        self._tools[name] = ToolDef(
            name=name,
            fn=fn,
            confirmable=confirmable,
            description=description,
            args_schema=args_schema
        )

    def get(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDef]:
        """列出所有工具"""
        return self._tools.copy()

    def is_confirmable(self, name: str) -> bool:
        """检查工具是否需要确认"""
        tool = self._tools.get(name)
        return tool.confirmable if tool else False


# 全局实例
tool_system = ToolSystem()
```

- [ ] **Step 2: 创建测试文件**

```python
"""agent/test_tool_system.py"""
import pytest
from agent.tool_system import ToolSystem, ToolDef


def dummy_echo(msg: str) -> dict:
    return {"msg": msg}


def dummy_modify(path: str) -> dict:
    return {"path": path}


class TestToolSystem:
    def test_register_and_get(self):
        ts = ToolSystem()
        ts.register("echo", dummy_echo, description="echo message")
        tool = ts.get("echo")
        assert tool is not None
        assert tool.name == "echo"
        assert tool.description == "echo message"

    def test_list_tools(self):
        ts = ToolSystem()
        ts.register("echo", dummy_echo)
        ts.register("modify", dummy_modify, confirmable=True)
        tools = ts.list_tools()
        assert len(tools) == 2
        assert tools["echo"].confirmable is False
        assert tools["modify"].confirmable is True

    def test_is_confirmable(self):
        ts = ToolSystem()
        ts.register("safe", dummy_echo)
        ts.register("danger", dummy_modify, confirmable=True)
        assert ts.is_confirmable("safe") is False
        assert ts.is_confirmable("danger") is True
        assert ts.is_confirmable("nonexistent") is False
```

- [ ] **Step 3: 运行测试验证**

```bash
cd D:\PROJECTS\CookieRookie
python -m pytest agent/test_tool_system.py -v
```

Expected: 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add agent/tool_system.py agent/test_tool_system.py
git commit -m "feat: add plugin-based ToolSystem for tool registration"
```

---

## Task 2: 基础文件工具（重构成使用 ToolSystem）

**Files:**
- Modify: `agent/tools.py` (重构，改用 ToolSystem)
- Modify: `agent/__init__.py` (更新导出)

- [ ] **Step 1: 重构 tools.py 使用 ToolSystem**

```python
"""
Debug Agent 工具集 - 重构为使用 ToolSystem
"""

import os
import re
import subprocess
import glob
import fnmatch
from typing import Dict, Callable, List
from .tool_system import tool_system


# ========== 工具实现 ==========

def read_file(path: str, offset: int = 1, limit: int = 100) -> dict:
    """读取文件内容 (按行号)"""
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
    """编辑文件"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        edit_mode = None

        if line is not None:
            if line < 1 or line > len(lines):
                return {"success": False, "error": f"Line {line} out of range (1-{len(lines)})"}
            lines[line - 1] = new_string + "\n" if not new_string.endswith("\n") else new_string
            edit_mode = "line"
        elif old_string is not None:
            content = "".join(lines)
            if old_string not in content:
                return {"success": False, "error": "old_string not found in file"}
            content = content.replace(old_string, new_string, 1)
            lines = content.splitlines(keepends=True)
            edit_mode = "old_string"
        else:
            return {"success": False, "error": "Must provide either line or old_string"}

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        preview_new = None
        if line is not None and 1 <= line <= len(lines):
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


def write_file(path: str, content: str) -> dict:
    """写入文件（新建或覆盖）"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "path": path,
            "bytes": len(content)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def exec(command: str, workdir: str = None, timeout: int = 30) -> dict:
    """执行 shell 命令"""
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
    """搜索文件中的关键词"""
    try:
        matches = []
        glob_pattern = os.path.join(path, "**", file_glob)
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
                            if pattern in text:
                                matched = True
                        if matched:
                            matches.append({
                                "file": filepath,
                                "line": i,
                                "content": text.strip(),
                            })
            except:
                continue

        return {
            "success": True,
            "matches": matches[:50],
            "count": len(matches)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_files(pattern: str, path: str = ".", use_regex: bool = False) -> dict:
    """查找文件"""
    try:
        matches: List[str] = []

        for root, dirs, files in os.walk(path):
            for filename in files:
                if use_regex:
                    if re.search(pattern, filename):
                        matches.append(os.path.join(root, filename))
                else:
                    rel_path = os.path.relpath(os.path.join(root, filename), path)
                    rel_path_norm = rel_path.replace("\\", "/")

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

def register_base_tools():
    """注册基础工具到 ToolSystem"""
    tool_system.register(
        "read_file",
        read_file,
        confirmable=False,
        description="读取文件内容",
        args_schema={"path": str, "offset": int, "limit": int}
    )
    tool_system.register(
        "edit_file",
        edit_file,
        confirmable=True,
        description="编辑文件（按行号或字符串替换）",
        args_schema={"path": str, "line": int, "new_string": str, "old_string": str}
    )
    tool_system.register(
        "write_file",
        write_file,
        confirmable=True,
        description="写入文件（新建或覆盖）",
        args_schema={"path": str, "content": str}
    )
    tool_system.register(
        "exec",
        exec,
        confirmable=True,
        description="执行 shell 命令",
        args_schema={"command": str, "workdir": str, "timeout": int}
    )
    tool_system.register(
        "search_files",
        search_files,
        confirmable=False,
        description="搜索文件中的关键词",
        args_schema={"pattern": str, "path": str, "file_glob": str}
    )
    tool_system.register(
        "find_files",
        find_files,
        confirmable=False,
        description="查找文件",
        args_schema={"pattern": str, "path": str}
    )


def register_tools() -> Dict[str, Callable]:
    """注册所有可用工具（兼容旧接口）"""
    register_base_tools()
    return {
        "read_file": read_file,
        "edit_file": edit_file,
        "write_file": write_file,
        "exec": exec,
        "search_files": search_files,
        "find_files": find_files,
    }
```

- [ ] **Step 2: 更新 __init__.py**

```python
"""agent/__init__.py"""
from .core import DebugAgent, InteractiveAgent, create_agent
from .tool_system import tool_system, ToolSystem

__all__ = [
    "DebugAgent",
    "InteractiveAgent",
    "create_agent",
    "tool_system",
    "ToolSystem",
]
```

- [ ] **Step 3: 运行现有测试确保兼容**

```bash
python -m pytest test/ -v
```

Expected: 现有测试全部 PASS

- [ ] **Step 4: Commit**

```bash
git add agent/tools.py agent/__init__.py
git commit -m "refactor: migrate tools.py to use ToolSystem"
```

---

## Task 3: InteractiveAgent 核心类

**Files:**
- Modify: `agent/core.py` (新增 InteractiveAgent)
- Test: `agent/test_interactive_agent.py`

- [ ] **Step 1: 添加 InteractiveAgent 类到 core.py**

在 `DebugAgent` 类后添加：

```python
class InteractiveAgent:
    """交互式 Coding Agent - 混合模式（自主执行 + 关键步骤确认）"""

    def __init__(self, llm_client, tool_system, max_iterations: int = 50):
        self.llm = llm_client
        self.tool_system = tool_system
        self.max_iterations = max_iterations
        self.pending_action = None  # 待确认的 action
        self.user_modifications = None  # 用户修改过的参数

    SYSTEM_PROMPT = """你是一个 Coding Agent。你的任务是理解用户需求，通过工具完成编码任务。

## 工作流程
1. 理解用户需求
2. 规划实现步骤
3. 执行计划（需要确认的操作会暂停等待用户）
4. 验证结果

## 可用工具（已注册）
{tool_list}

## 确认机制
标记为 confirmable=True 的工具在执行前需要用户确认。
用户可以：/confirm 确认 /reject 拒绝并让你重新规划 /edit 修改参数

## 输出格式（严格遵守！）

需要执行操作时：
```
thought: 你的推理过程
action: 工具名(参数1="值1", 参数2="值2")
done: false
```

任务完成时：
```
thought: 已完成
done: true
summary: 任务总结
```

## 重要规则
1. 先规划，再执行
2. 优先使用 confirmable=False 的工具减少确认
3. 修改代码前先读文件
4. 每次修改后验证结果"""

    def _build_tool_list(self) -> str:
        """构建工具列表供 LLM 参考"""
        lines = []
        for name, tool in self.tool_system.list_tools().items():
            confirm = " [需要确认]" if tool.confirmable else ""
            lines.append(f"- {name}: {tool.description}{confirm}")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT.format(tool_list=self._build_tool_list())

    def run(self, task: str) -> str:
        """运行 Agent（混合模式入口）"""
        context = self._build_initial_context(task)

        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")

            # 如果有待确认的 action，先展示给用户
            if self.pending_action:
                self._show_pending_action()
                return "awaiting_confirmation"

            # LLM 推理
            response = self.llm.chat(context)

            # 解析响应
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            print(f"Thought: {reasoning}")

            if done:
                return summary or "Task completed!"

            if not action:
                print(f"Warning: No action in response")
                return f"LLM did not provide action. Response: {response}"

            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            # 检查是否需要确认
            if self.tool_system.is_confirmable(tool_name):
                self.pending_action = {
                    "action": action,
                    "reasoning": reasoning,
                    "iteration": i + 1
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            # 直接执行
            result = self._execute_tool(tool_name, tool_args)
            context = self._update_context(context, action, result, reasoning, i + 1)

        return "Max iterations reached"

    def confirm(self) -> str:
        """用户确认，执行 pending action"""
        if not self.pending_action:
            return "No pending action to confirm"

        action = self.pending_action["action"]
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        iteration = self.pending_action["iteration"]
        reasoning = self.pending_action["reasoning"]

        result = self._execute_tool(tool_name, tool_args)

        # 更新 context（需要重建因为 run 已经返回）
        context = {
            "task": self.pending_action.get("task", ""),
            "history": [],
            "system": self._build_system_prompt()
        }

        # 从 history 重建
        for h in self.pending_action.get("history", []):
            context["history"].append(h)

        context = self._update_context(context, action, result, reasoning, iteration)

        self.pending_action = None

        # 继续执行
        return self._continue_loop(context, iteration)

    def reject(self, new_instructions: str = None) -> str:
        """用户拒绝，重新规划"""
        if not self.pending_action:
            return "No pending action to reject"

        context = {
            "task": self.pending_action.get("task", ""),
            "history": self.pending_action.get("history", []),
            "system": self._build_system_prompt(),
            "rejection_note": new_instructions or "用户拒绝了上一步操作，请重新规划"
        }

        self.pending_action = None
        return self._continue_loop(context, 0)

    def edit_and_confirm(self, modified_args: dict) -> str:
        """用户修改参数后确认"""
        if not self.pending_action:
            return "No pending action to edit"

        self.pending_action["action"]["args"].update(modified_args)
        self.pending_action["modified_args"] = modified_args
        return self.confirm()

    def _show_pending_action(self):
        """展示待确认的 action"""
        action = self.pending_action["action"]
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        reasoning = self.pending_action["reasoning"]

        print("\n" + "=" * 50)
        print("需要确认的操作：")
        print(f"  Thought: {reasoning}")
        print(f"  Action: {tool_name}")
        for k, v in tool_args.items():
            print(f"    {k}: {v}")
        print("=" * 50)
        print("选项: /confirm 确认 | /reject 拒绝 | /edit key=value 修改参数")
        print("=" * 50 + "\n")

    def _execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        """执行工具"""
        print(f"Executing: {tool_name}({tool_args})")
        tool_def = self.tool_system.get(tool_name)
        if not tool_def:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        try:
            result = tool_def.fn(**tool_args)
            result_summary = str(result)[:200]
            print(f"Result: {result_summary}")
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_context(self, context: dict, action: dict, result: dict,
                       reasoning: str, iteration: int) -> dict:
        """更新 context"""
        context["history"].append({
            "action": action,
            "result": result,
            "thought": reasoning,
            "iteration": iteration
        })
        return context

    def _continue_loop(self, context: dict, start_iteration: int) -> str:
        """继续执行循环"""
        for i in range(start_iteration, self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")

            if self.pending_action:
                self._show_pending_action()
                return "awaiting_confirmation"

            response = self.llm.chat(context)

            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            print(f"Thought: {reasoning}")

            if done:
                return summary or "Task completed!"

            if not action:
                return f"LLM did not provide action. Response: {response}"

            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            if self.tool_system.is_confirmable(tool_name):
                self.pending_action = {
                    "action": action,
                    "reasoning": reasoning,
                    "iteration": i + 1,
                    "task": context.get("task", ""),
                    "history": context.get("history", [])
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            result = self._execute_tool(tool_name, tool_args)
            context = self._update_context(context, action, result, reasoning, i + 1)

        return "Max iterations reached"

    def _build_initial_context(self, task: str) -> dict:
        """构建初始 context"""
        return {
            "task": task,
            "history": [],
            "system": self._build_system_prompt()
        }


def create_agent(llm_client, max_iterations: int = 50) -> DebugAgent:
    """创建 Debug Agent（兼容旧接口）"""
    return DebugAgent(llm_client, max_iterations)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50) -> InteractiveAgent:
    """创建 Interactive Agent"""
    return InteractiveAgent(llm_client, tool_system, max_iterations)
```

- [ ] **Step 2: 创建测试文件**

```python
"""agent/test_interactive_agent.py"""
import pytest
from unittest.mock import MagicMock


class MockToolSystem:
    def __init__(self):
        self.tools = {}
        self.confirmable_map = {}

    def register(self, name, fn, confirmable=False, description="", args_schema=None):
        self.tools[name] = fn
        self.confirmable_map[name] = confirmable

    def get(self, name):
        return MagicMock(fn=self.tools.get(name)) if name in self.tools else None

    def list_tools(self):
        return {name: MagicMock(fn=fn, confirmable=self.confirmable_map.get(name, False),
                                description="")
                for name, fn in self.tools.items()}

    def is_confirmable(self, name):
        return self.confirmable_map.get(name, False)


class TestInteractiveAgent:
    def test_initialization(self):
        from agent.core import InteractiveAgent

        mock_llm = MagicMock()
        mock_ts = MockToolSystem()

        agent = InteractiveAgent(mock_llm, mock_ts, max_iterations=10)

        assert agent.llm == mock_llm
        assert agent.tool_system == mock_ts
        assert agent.max_iterations == 10
        assert agent.pending_action is None

    def test_build_tool_list(self):
        from agent.core import InteractiveAgent

        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("read_file", lambda x: x, confirmable=False, description="read file")
        mock_ts.register("edit_file", lambda x: x, confirmable=True, description="edit file")

        agent = InteractiveAgent(mock_llm, mock_ts)

        tool_list = agent._build_tool_list()
        assert "read_file" in tool_list
        assert "edit file [需要确认]" in tool_list

    def test_pending_action_flow(self):
        from agent.core import InteractiveAgent

        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("exec", lambda cmd: {"success": True}, confirmable=True, description="execute")

        agent = InteractiveAgent(mock_llm, mock_ts)

        # 模拟 LLM 返回需要确认的 action
        mock_llm.chat.return_value = {
            "thought": "need to execute command",
            "action": {"tool": "exec", "args": {"command": "rm -rf /"}},
            "done": False
        }

        result = agent.run("test task")

        assert result == "awaiting_confirmation"
        assert agent.pending_action is not None
        assert agent.pending_action["action"]["tool"] == "exec"
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest agent/test_interactive_agent.py -v
```

Expected: tests PASS

- [ ] **Step 4: Commit**

```bash
git add agent/core.py agent/test_interactive_agent.py
git commit -m "feat: add InteractiveAgent with confirmation mechanism"
```

---

## Task 4: test_tools.py - 测试框架

**Files:**
- Create: `agent/test_tools.py`
- Test: `agent/test_test_tools.py`

- [ ] **Step 1: 创建 test_tools.py**

```python
"""
测试工具集 - 执行和生成测试用例
"""

import os
import subprocess
import fnmatch
from typing import Optional, Dict, Any


# ========== 工具实现 ==========

def test_run(path: Optional[str] = None, pattern: str = "test_*.py",
             framework: Optional[str] = None) -> dict:
    """
    执行测试

    Args:
        path: 测试路径（文件或目录），默认当前目录
        pattern: 文件匹配模式
        framework: 测试框架（auto/pytest/unittest/none），auto 自动检测
    """
    path = path or "."
    framework = framework or "auto"

    # 检测框架
    if framework == "auto":
        framework = _detect_framework(path)

    if framework == "none":
        return {"success": False, "error": "No test framework detected"}

    # 构建命令
    if framework == "pytest":
        cmd = f"pytest {path}"
    elif framework == "unittest":
        cmd = f"python -m unittest {path}"
    elif framework == "jest":
        cmd = f"jest {path}"
    elif framework == "go":
        cmd = f"go test {path}"
    else:
        return {"success": False, "error": f"Unsupported framework: {framework}"}

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "framework": framework,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "passed": _parse_passed(result.stdout),
            "failed": _parse_failed(result.stdout),
            "errors": _parse_errors(result.stdout)
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Test timeout after 120s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_generate(source: str, target: Optional[str] = None,
                  framework: str = "pytest") -> dict:
    """
    生成测试用例（由 LLM 生成，这里只做框架占位）

    实际生成依赖 LLM 调用
    """
    if not os.path.exists(source):
        return {"success": False, "error": f"Source file not found: {source}"}

    if target is None:
        # 自动推导 target 路径
        dir_name = os.path.dirname(source)
        base_name = os.path.basename(source)
        test_name = f"test_{base_name}"
        if dir_name:
            target = os.path.join(dir_name.replace("src", "tests"), test_name)
        else:
            target = test_name

    return {
        "success": True,
        "source": source,
        "target": target,
        "framework": framework,
        "message": f"生成测试用例到 {target}，框架: {framework}"
    }


def _detect_framework(path: str) -> str:
    """自动检测测试框架"""
    if os.path.isfile(path):
        dir_path = os.path.dirname(path)
    else:
        dir_path = path

    # 检查 pytest
    if os.path.exists(os.path.join(dir_path, "pytest.ini")):
        return "pytest"
    if os.path.exists(os.path.join(dir_path, "pyproject.toml")):
        with open(os.path.join(dir_path, "pyproject.toml"), "r") as f:
            content = f.read()
            if "[tool.pytest" in content:
                return "pytest"

    # 检查 unittest
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if fnmatch.fnmatch(f, "test_*.py") or fnmatch.fnmatch(f, "*_test.py"):
                with open(os.path.join(root, f), "r") as fp:
                    content = fp.read()
                    if "unittest" in content or "TestCase" in content:
                        return "unittest"

    # 默认 pytest（最常用）
    return "pytest"


def _parse_passed(output: str) -> int:
    """从输出解析通过的测试数"""
    import re
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


def _parse_failed(output: str) -> int:
    """从输出解析失败的测试数"""
    import re
    match = re.search(r"(\d+) failed", output)
    return int(match.group(1)) if match else 0


def _parse_errors(output: str) -> int:
    """从输出解析错误的测试数"""
    import re
    match = re.search(r"(\d+) error", output)
    return int(match.group(1)) if match else 0
```

- [ ] **Step 2: 创建测试**

```python
"""agent/test_test_tools.py"""
import pytest
import os
import tempfile
from agent.test_tools import test_run, test_generate, _detect_framework


class TestTestTools:
    def test_detect_pytest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 pytest.ini
            with open(os.path.join(tmpdir, "pytest.ini"), "w") as f:
                f.write("[pytest]\n")

            framework = _detect_framework(tmpdir)
            assert framework == "pytest"

    def test_detect_unittest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 test 文件
            test_file = os.path.join(tmpdir, "test_sample.py")
            with open(test_file, "w") as f:
                f.write("import unittest\nclass TestSample(unittest.TestCase):\n    pass\n")

            framework = _detect_framework(tmpdir)
            assert framework == "unittest"

    def test_test_run_invalid_path(self):
        result = test_run(path="/nonexistent/path/xyz")
        assert result["success"] is False
        assert "error" in result

    def test_test_generate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建源文件
            source = os.path.join(tmpdir, "calculator.py")
            with open(source, "w") as f:
                f.write("def add(a, b): return a + b\n")

            result = test_generate(source=source)
            assert result["success"] is True
            assert result["source"] == source
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest agent/test_test_tools.py -v
```

Expected: tests PASS

- [ ] **Step 4: Commit**

```bash
git add agent/test_tools.py agent/test_test_tools.py
git commit -m "feat: add test_tools for test execution and generation"
```

---

## Task 5: git_tools.py - Git 工具集

**Files:**
- Create: `agent/git_tools.py`
- Test: `agent/test_git_tools.py`

- [ ] **Step 1: 创建 git_tools.py**

```python
"""
Git 工具集
"""

import subprocess
import os
from typing import Optional, List


def git_status() -> dict:
    """获取 Git 状态"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {
            "success": True,
            "files": [line.strip() for line in lines],
            "count": len(lines),
            "clean": len(lines) == 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_diff(path: Optional[str] = None) -> dict:
    """获取 Git diff"""
    try:
        cmd = ["git", "diff"]
        if path:
            cmd.append(path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return {
            "success": True,
            "diff": result.stdout,
            "returncode": result.returncode
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_commit(message: str, files: Optional[List[str]] = None) -> dict:
    """提交更改"""
    try:
        # 先 add
        if files:
            subprocess.run(["git", "add"] + files, check=True)
        else:
            subprocess.run(["git", "add", "-A"], check=True)

        # 再 commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "returncode": result.returncode
            }

        return {
            "success": True,
            "message": message,
            "output": result.stdout
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_branch(list_branches: bool = False) -> dict:
    """Git branch 操作"""
    try:
        if list_branches:
            result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True
            )
            branches = [b.strip() for b in result.stdout.split("\n") if b.strip()]
            current = None
            for b in branches:
                if b.startswith("*"):
                    current = b[1:].strip()
                    branches.remove(b)
                    branches.insert(0, current)
                    break

            return {
                "success": True,
                "branches": branches,
                "current": current
            }
        else:
            return {"success": False, "error": "Specify operation"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_log(limit: int = 10) -> dict:
    """获取 Git 日志"""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-n{limit}"],
            capture_output=True,
            text=True
        )
        commits = [c.strip() for c in result.stdout.split("\n") if c.strip()]
        return {
            "success": True,
            "commits": commits,
            "count": len(commits)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_checkout(branch: str, create: bool = False) -> dict:
    """切换分支"""
    try:
        cmd = ["git", "checkout"]
        if create:
            cmd.append("-b")
        cmd.append(branch)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "returncode": result.returncode
            }

        return {
            "success": True,
            "branch": branch,
            "output": result.stdout
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 2: 创建测试**

```python
"""agent/test_git_tools.py"""
import pytest
import os
import tempfile
import subprocess
from agent.git_tools import git_status, git_diff, git_log


class TestGitTools:
    def test_git_status(self):
        # 在 git 仓库中测试
        result = git_status()
        assert "success" in result
        assert "files" in result
        assert "count" in result
        assert "clean" in result

    def test_git_log(self):
        result = git_log(limit=5)
        assert "success" in result or "error" in result
        # 在 git 仓库中应该有 commits

    def test_git_diff(self):
        result = git_diff()
        assert "success" in result
        assert "diff" in result
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest agent/test_git_tools.py -v
```

Expected: tests PASS (在 git 仓库中)

- [ ] **Step 4: Commit**

```bash
git add agent/git_tools.py agent/test_git_tools.py
git commit -m "feat: add git_tools for Git operations"
```

---

## Task 6: 集成测试

**Files:**
- Create: `agent/test_integration.py`

- [ ] **Step 1: 创建集成测试**

```python
"""agent/test_integration.py"""
import pytest
from unittest.mock import MagicMock, patch
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
from agent import tools


class TestIntegration:
    def test_full_tool_system_setup(self):
        """测试完整工具系统初始化"""
        # 清空并重新注册
        from agent import tools as tools_module
        tools_module.register_base_tools()

        registered = tool_system.list_tools()
        assert "read_file" in registered
        assert "edit_file" in registered
        assert "write_file" in registered
        assert "exec" in registered
        assert "search_files" in registered
        assert "find_files" in registered

    def test_confirmable_flags(self):
        """测试 confirmable 标志"""
        from agent import tools as tools_module
        tools_module.register_base_tools()

        assert tool_system.is_confirmable("read_file") is False
        assert tool_system.is_confirmable("edit_file") is True
        assert tool_system.is_confirmable("write_file") is True
        assert tool_system.is_confirmable("exec") is True

    def test_interactive_agent_with_mock_llm(self):
        """测试 InteractiveAgent 与 mock LLM"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "thought": "test",
            "action": {"tool": "read_file", "args": {"path": "main.py"}},
            "done": False
        }

        from agent import tools as tools_module
        tools_module.register_base_tools()

        agent = InteractiveAgent(mock_llm, tool_system, max_iterations=1)
        result = agent.run("read main.py")

        assert result == "awaiting_confirmation"
        assert agent.pending_action is not None
```

- [ ] **Step 2: 运行集成测试**

```bash
python -m pytest agent/test_integration.py -v
```

Expected: tests PASS

- [ ] **Step 3: Commit**

```bash
git add agent/test_integration.py
git commit -m "test: add integration tests"
```

---

## Task 7: main.py 入口更新

**Files:**
- Modify: `main.py` (添加 --interactive 模式)

- [ ] **Step 1: 更新 main.py 支持交互模式**

在 main.py 末尾添加：

```python
def interactive_main():
    """交互模式入口"""
    import readline  # 支持上下箭头

    config = load_config()

    if not config["api_key"]:
        print("Error: ANTHROPIC_API_KEY not found in .env")
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print("Type 'exit' to quit, 'help' for commands\n")

    # 初始化组件
    from agent.tool_system import tool_system
    from agent import tools as tools_module
    tools_module.register_base_tools()

    from agent.core import create_interactive_agent

    llm_client = LLMClient(
        config["api_key"],
        config["model"],
        config["base_url"]
    )
    agent = create_interactive_agent(llm_client, tool_system)

    current_task = None

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                break

            if user_input == "/confirm":
                if agent.pending_action:
                    result = agent.confirm()
                    print(f"\n{result}\n")
                else:
                    print("No pending action")
                continue

            if user_input.startswith("/reject"):
                parts = user_input.split(" ", 1)
                instructions = parts[1] if len(parts) > 1 else None
                result = agent.reject(instructions)
                print(f"\n{result}\n")
                continue

            if user_input.startswith("/edit"):
                # /edit key=value key2=value2
                parts = user_input[5:].strip()
                modifications = {}
                for part in parts.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        modifications[k] = v
                if modifications and agent.pending_action:
                    result = agent.edit_and_confirm(modifications)
                    print(f"\n{result}\n")
                else:
                    print("Invalid /edit usage or no pending action")
                continue

            if user_input == "/status":
                print(f"Pending action: {agent.pending_action is not None}")
                if agent.pending_action:
                    print(f"Tool: {agent.pending_action['action']['tool']}")
                continue

            # 普通任务
            current_task = user_input
            result = agent.run(user_input)

            if result == "awaiting_confirmation":
                # 等待用户在下一轮确认
                pass
            else:
                print(f"\n{result}\n")

        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")
```

在 `if __name__ == "__main__":` 块中添加：

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_main()
    else:
        main()
```

- [ ] **Step 2: 测试 --interactive 模式（手动测试）**

```bash
python main.py --interactive
# 输入 help 查看命令
# 输入 exit 退出
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add --interactive mode for collaborative coding"
```

---

## 执行顺序

| 顺序 | Task | 描述 |
|------|------|------|
| 1 | Task 1 | ToolSystem 插件化工具注册表 |
| 2 | Task 2 | 基础文件工具（重构成使用 ToolSystem）|
| 3 | Task 3 | InteractiveAgent 核心类 |
| 4 | Task 4 | test_tools.py - 测试框架 |
| 5 | Task 5 | git_tools.py - Git 工具集 |
| 6 | Task 6 | 集成测试 |
| 7 | Task 7 | main.py 入口更新 |

---

## 预期产出

完成后 CookieRookie 将具备：
- ✅ 插件化工具系统
- ✅ 交互式确认机制（/confirm /reject /edit）
- ✅ 测试执行和生成能力
- ✅ Git 操作能力
- ✅ 向后兼容（Debug Agent 模式继续可用）
