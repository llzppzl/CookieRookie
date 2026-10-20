# CookieRookie Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn CookieRookie from a Debug Agent into a general-purpose Coding Agent, with a hybrid interaction mode (autonomous execution + confirmation), test execution/generation, and Git integration

**Architecture:** The core is the InteractiveAgent class, which handles task planning, the execution loop, and the confirmation mechanism. The tool system is refactored into a plugin-style registry (ToolSystem) that supports a confirmable flag. Backward compatibility is kept: existing DebugAgent features remain available.

**Tech Stack:** Python 3, requests, subprocess (standard library)

---

## File Structure

```
agent/
├── __init__.py              # Exports InteractiveAgent, ToolSystem
├── core.py                  # DebugAgent → InteractiveAgent (refactor)
├── tools.py                 # Tool registry (refactor, delegates to ToolSystem)
├── tool_system.py           # New: plugin-style tool system
├── git_tools.py             # New: Git toolset
├── test_tools.py            # New: test toolset
└── __pycache__/            # (auto-generated)

docs/superpowers/plans/      # This plan
docs/superpowers/specs/     # Design docs

main.py                      # Unchanged
```

---

## Task 1: ToolSystem Plugin-Style Tool Registry

**Files:**
- Create: `agent/tool_system.py`
- Test: `agent/test_tool_system.py`

- [ ] **Step 1: Create the tool_system.py skeleton**

```python
"""
ToolSystem - plugin-style tool registry
"""

from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDef:
    """Tool definition"""
    name: str
    fn: Callable
    confirmable: bool = False
    description: str = ""
    args_schema: Optional[Dict[str, Any]] = None


class ToolSystem:
    """Tool registration and management"""

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
        """Register a tool"""
        self._tools[name] = ToolDef(
            name=name,
            fn=fn,
            confirmable=confirmable,
            description=description,
            args_schema=args_schema
        )

    def get(self, name: str) -> Optional[ToolDef]:
        """Get a tool definition"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDef]:
        """List all tools"""
        return self._tools.copy()

    def is_confirmable(self, name: str) -> bool:
        """Check whether a tool requires confirmation"""
        tool = self._tools.get(name)
        return tool.confirmable if tool else False


# Global instance
tool_system = ToolSystem()
```

- [ ] **Step 2: Create the test file**

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

- [ ] **Step 3: Run the tests to verify**

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

## Task 2: Basic File Tools (Refactored to Use ToolSystem)

**Files:**
- Modify: `agent/tools.py` (refactor to use ToolSystem)
- Modify: `agent/__init__.py` (update exports)

- [ ] **Step 1: Refactor tools.py to use ToolSystem**

```python
"""
Debug Agent toolset - refactored to use ToolSystem
"""

import os
import re
import subprocess
import glob
import fnmatch
from typing import Dict, Callable, List
from .tool_system import tool_system


# ========== Tool implementations ==========

def read_file(path: str, offset: int = 1, limit: int = 100) -> dict:
    """Read file contents (by line number)"""
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
    """Edit a file"""
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
    """Write a file (create or overwrite)"""
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
    """Run a shell command"""
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
    """Search files for a keyword"""
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
    """Find files"""
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


# ========== Tool registration ==========

def register_base_tools():
    """Register the basic tools with ToolSystem"""
    tool_system.register(
        "read_file",
        read_file,
        confirmable=False,
        description="Read file contents",
        args_schema={"path": str, "offset": int, "limit": int}
    )
    tool_system.register(
        "edit_file",
        edit_file,
        confirmable=True,
        description="Edit a file (by line number or string replacement)",
        args_schema={"path": str, "line": int, "new_string": str, "old_string": str}
    )
    tool_system.register(
        "write_file",
        write_file,
        confirmable=True,
        description="Write a file (create or overwrite)",
        args_schema={"path": str, "content": str}
    )
    tool_system.register(
        "exec",
        exec,
        confirmable=True,
        description="Run a shell command",
        args_schema={"command": str, "workdir": str, "timeout": int}
    )
    tool_system.register(
        "search_files",
        search_files,
        confirmable=False,
        description="Search files for a keyword",
        args_schema={"pattern": str, "path": str, "file_glob": str}
    )
    tool_system.register(
        "find_files",
        find_files,
        confirmable=False,
        description="Find files",
        args_schema={"pattern": str, "path": str}
    )


def register_tools() -> Dict[str, Callable]:
    """Register all available tools (compatible with the old interface)"""
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

- [ ] **Step 2: Update __init__.py**

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

- [ ] **Step 3: Run the existing tests to ensure compatibility**

```bash
python -m pytest test/ -v
```

Expected: all existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add agent/tools.py agent/__init__.py
git commit -m "refactor: migrate tools.py to use ToolSystem"
```

---

## Task 3: InteractiveAgent Core Class

**Files:**
- Modify: `agent/core.py` (add InteractiveAgent)
- Test: `agent/test_interactive_agent.py`

- [ ] **Step 1: Add the InteractiveAgent class to core.py**

Add after the `DebugAgent` class:

```python
class InteractiveAgent:
    """Interactive Coding Agent - hybrid mode (autonomous execution + confirmation of key steps)"""

    def __init__(self, llm_client, tool_system, max_iterations: int = 50):
        self.llm = llm_client
        self.tool_system = tool_system
        self.max_iterations = max_iterations
        self.pending_action = None  # Action awaiting confirmation
        self.user_modifications = None  # Parameters modified by the user

    SYSTEM_PROMPT = """You are a Coding Agent. Your job is to understand the user's request and complete coding tasks using tools.

## Workflow
1. Understand the user's request
2. Plan the implementation steps
3. Execute the plan (operations that need confirmation pause and wait for the user)
4. Verify the results

## Available tools (registered)
{tool_list}

## Confirmation mechanism
Tools marked confirmable=True require user confirmation before execution.
The user can: /confirm to confirm, /reject to reject and have you re-plan, /edit to modify parameters

## Output format (follow strictly!)

When you need to perform an operation:
```
thought: your reasoning
action: tool_name(param1="value1", param2="value2")
done: false
```

When the task is complete:
```
thought: completed
done: true
summary: task summary
```

## Important rules
1. Plan first, then execute
2. Prefer tools with confirmable=False to reduce confirmations
3. Read a file before modifying code
4. Verify the result after each change"""

    def _build_tool_list(self) -> str:
        """Build the tool list for the LLM's reference"""
        lines = []
        for name, tool in self.tool_system.list_tools().items():
            confirm = " [needs confirmation]" if tool.confirmable else ""
            lines.append(f"- {name}: {tool.description}{confirm}")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT.format(tool_list=self._build_tool_list())

    def run(self, task: str) -> str:
        """Run the Agent (hybrid mode entry point)"""
        context = self._build_initial_context(task)

        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")

            # If there is an action awaiting confirmation, show it to the user first
            if self.pending_action:
                self._show_pending_action()
                return "awaiting_confirmation"

            # LLM reasoning
            response = self.llm.chat(context)

            # Parse the response
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

            # Check whether confirmation is needed
            if self.tool_system.is_confirmable(tool_name):
                self.pending_action = {
                    "action": action,
                    "reasoning": reasoning,
                    "iteration": i + 1
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            # Execute directly
            result = self._execute_tool(tool_name, tool_args)
            context = self._update_context(context, action, result, reasoning, i + 1)

        return "Max iterations reached"

    def confirm(self) -> str:
        """User confirmed: execute the pending action"""
        if not self.pending_action:
            return "No pending action to confirm"

        action = self.pending_action["action"]
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        iteration = self.pending_action["iteration"]
        reasoning = self.pending_action["reasoning"]

        result = self._execute_tool(tool_name, tool_args)

        # Update context (needs rebuilding because run has already returned)
        context = {
            "task": self.pending_action.get("task", ""),
            "history": [],
            "system": self._build_system_prompt()
        }

        # Rebuild from history
        for h in self.pending_action.get("history", []):
            context["history"].append(h)

        context = self._update_context(context, action, result, reasoning, iteration)

        self.pending_action = None

        # Continue execution
        return self._continue_loop(context, iteration)

    def reject(self, new_instructions: str = None) -> str:
        """User rejected: re-plan"""
        if not self.pending_action:
            return "No pending action to reject"

        context = {
            "task": self.pending_action.get("task", ""),
            "history": self.pending_action.get("history", []),
            "system": self._build_system_prompt(),
            "rejection_note": new_instructions or "The user rejected the previous operation. Please re-plan."
        }

        self.pending_action = None
        return self._continue_loop(context, 0)

    def edit_and_confirm(self, modified_args: dict) -> str:
        """User modified parameters, then confirmed"""
        if not self.pending_action:
            return "No pending action to edit"

        self.pending_action["action"]["args"].update(modified_args)
        self.pending_action["modified_args"] = modified_args
        return self.confirm()

    def _show_pending_action(self):
        """Show the action awaiting confirmation"""
        action = self.pending_action["action"]
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        reasoning = self.pending_action["reasoning"]

        print("\n" + "=" * 50)
        print("Operation requiring confirmation:")
        print(f"  Thought: {reasoning}")
        print(f"  Action: {tool_name}")
        for k, v in tool_args.items():
            print(f"    {k}: {v}")
        print("=" * 50)
        print("Options: /confirm confirm | /reject reject | /edit key=value modify parameters")
        print("=" * 50 + "\n")

    def _execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool"""
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
        """Update context"""
        context["history"].append({
            "action": action,
            "result": result,
            "thought": reasoning,
            "iteration": iteration
        })
        return context

    def _continue_loop(self, context: dict, start_iteration: int) -> str:
        """Continue the execution loop"""
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
        """Build the initial context"""
        return {
            "task": task,
            "history": [],
            "system": self._build_system_prompt()
        }


def create_agent(llm_client, max_iterations: int = 50) -> DebugAgent:
    """Create a Debug Agent (compatible with the old interface)"""
    return DebugAgent(llm_client, max_iterations)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50) -> InteractiveAgent:
    """Create an Interactive Agent"""
    return InteractiveAgent(llm_client, tool_system, max_iterations)
```

- [ ] **Step 2: Create the test file**

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
        assert "edit file [needs confirmation]" in tool_list

    def test_pending_action_flow(self):
        from agent.core import InteractiveAgent

        mock_llm = MagicMock()
        mock_ts = MockToolSystem()
        mock_ts.register("exec", lambda cmd: {"success": True}, confirmable=True, description="execute")

        agent = InteractiveAgent(mock_llm, mock_ts)

        # Simulate the LLM returning an action that needs confirmation
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

- [ ] **Step 3: Run the tests**

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

## Task 4: test_tools.py - Test Framework

**Files:**
- Create: `agent/test_tools.py`
- Test: `agent/test_test_tools.py`

- [ ] **Step 1: Create test_tools.py**

```python
"""
Test toolset - run and generate test cases
"""

import os
import subprocess
import fnmatch
from typing import Optional, Dict, Any


# ========== Tool implementations ==========

def test_run(path: Optional[str] = None, pattern: str = "test_*.py",
             framework: Optional[str] = None) -> dict:
    """
    Run tests

    Args:
        path: test path (file or directory), defaults to the current directory
        pattern: file match pattern
        framework: test framework (auto/pytest/unittest/none); auto means auto-detect
    """
    path = path or "."
    framework = framework or "auto"

    # Detect the framework
    if framework == "auto":
        framework = _detect_framework(path)

    if framework == "none":
        return {"success": False, "error": "No test framework detected"}

    # Build the command
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
    Generate test cases (generated by the LLM; this is only a framework placeholder)

    Actual generation depends on an LLM call
    """
    if not os.path.exists(source):
        return {"success": False, "error": f"Source file not found: {source}"}

    if target is None:
        # Automatically derive the target path
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
        "message": f"Generating test cases into {target}, framework: {framework}"
    }


def _detect_framework(path: str) -> str:
    """Auto-detect the test framework"""
    if os.path.isfile(path):
        dir_path = os.path.dirname(path)
    else:
        dir_path = path

    # Check for pytest
    if os.path.exists(os.path.join(dir_path, "pytest.ini")):
        return "pytest"
    if os.path.exists(os.path.join(dir_path, "pyproject.toml")):
        with open(os.path.join(dir_path, "pyproject.toml"), "r") as f:
            content = f.read()
            if "[tool.pytest" in content:
                return "pytest"

    # Check for unittest
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if fnmatch.fnmatch(f, "test_*.py") or fnmatch.fnmatch(f, "*_test.py"):
                with open(os.path.join(root, f), "r") as fp:
                    content = fp.read()
                    if "unittest" in content or "TestCase" in content:
                        return "unittest"

    # Default to pytest (most common)
    return "pytest"


def _parse_passed(output: str) -> int:
    """Parse the number of passed tests from the output"""
    import re
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


def _parse_failed(output: str) -> int:
    """Parse the number of failed tests from the output"""
    import re
    match = re.search(r"(\d+) failed", output)
    return int(match.group(1)) if match else 0


def _parse_errors(output: str) -> int:
    """Parse the number of errored tests from the output"""
    import re
    match = re.search(r"(\d+) error", output)
    return int(match.group(1)) if match else 0
```

- [ ] **Step 2: Create the tests**

```python
"""agent/test_test_tools.py"""
import pytest
import os
import tempfile
from agent.test_tools import test_run, test_generate, _detect_framework


class TestTestTools:
    def test_detect_pytest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create pytest.ini
            with open(os.path.join(tmpdir, "pytest.ini"), "w") as f:
                f.write("[pytest]\n")

            framework = _detect_framework(tmpdir)
            assert framework == "pytest"

    def test_detect_unittest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the test file
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
            # Create the source file
            source = os.path.join(tmpdir, "calculator.py")
            with open(source, "w") as f:
                f.write("def add(a, b): return a + b\n")

            result = test_generate(source=source)
            assert result["success"] is True
            assert result["source"] == source
```

- [ ] **Step 3: Run the tests**

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

## Task 5: git_tools.py - Git Toolset

**Files:**
- Create: `agent/git_tools.py`
- Test: `agent/test_git_tools.py`

- [ ] **Step 1: Create git_tools.py**

```python
"""
Git toolset
"""

import subprocess
import os
from typing import Optional, List


def git_status() -> dict:
    """Get Git status"""
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
    """Get Git diff"""
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
    """Commit changes"""
    try:
        # First add
        if files:
            subprocess.run(["git", "add"] + files, check=True)
        else:
            subprocess.run(["git", "add", "-A"], check=True)

        # Then commit
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
    """Git branch operations"""
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
    """Get the Git log"""
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
    """Switch branches"""
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

- [ ] **Step 2: Create the tests**

```python
"""agent/test_git_tools.py"""
import pytest
import os
import tempfile
import subprocess
from agent.git_tools import git_status, git_diff, git_log


class TestGitTools:
    def test_git_status(self):
        # Test inside a git repository
        result = git_status()
        assert "success" in result
        assert "files" in result
        assert "count" in result
        assert "clean" in result

    def test_git_log(self):
        result = git_log(limit=5)
        assert "success" in result or "error" in result
        # Inside a git repository there should be commits

    def test_git_diff(self):
        result = git_diff()
        assert "success" in result
        assert "diff" in result
```

- [ ] **Step 3: Run the tests**

```bash
python -m pytest agent/test_git_tools.py -v
```

Expected: tests PASS (inside a git repository)

- [ ] **Step 4: Commit**

```bash
git add agent/git_tools.py agent/test_git_tools.py
git commit -m "feat: add git_tools for Git operations"
```

---

## Task 6: Integration Tests

**Files:**
- Create: `agent/test_integration.py`

- [ ] **Step 1: Create the integration tests**

```python
"""agent/test_integration.py"""
import pytest
from unittest.mock import MagicMock, patch
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
from agent import tools


class TestIntegration:
    def test_full_tool_system_setup(self):
        """Test full tool system initialization"""
        # Clear and re-register
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
        """Test the confirmable flag"""
        from agent import tools as tools_module
        tools_module.register_base_tools()

        assert tool_system.is_confirmable("read_file") is False
        assert tool_system.is_confirmable("edit_file") is True
        assert tool_system.is_confirmable("write_file") is True
        assert tool_system.is_confirmable("exec") is True

    def test_interactive_agent_with_mock_llm(self):
        """Test InteractiveAgent with a mock LLM"""
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

- [ ] **Step 2: Run the integration tests**

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

## Task 7: main.py Entry Point Update

**Files:**
- Modify: `main.py` (add --interactive mode)

- [ ] **Step 1: Update main.py to support interactive mode**

Add at the end of main.py:

```python
def interactive_main():
    """Interactive mode entry point"""
    import readline  # Supports up/down arrow keys

    config = load_config()

    if not config["api_key"]:
        print("Error: ANTHROPIC_API_KEY not found in .env")
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print("Type 'exit' to quit, 'help' for commands\n")

    # Initialize components
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

            # Regular task
            current_task = user_input
            result = agent.run(user_input)

            if result == "awaiting_confirmation":
                # Wait for the user to confirm in the next round
                pass
            else:
                print(f"\n{result}\n")

        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")
```

Add inside the `if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_main()
    else:
        main()
```

- [ ] **Step 2: Test --interactive mode (manual test)**

```bash
python main.py --interactive
# Type help to see commands
# Type exit to quit
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add --interactive mode for collaborative coding"
```

---

## Execution Order

| Order | Task | Description |
|------|------|------|
| 1 | Task 1 | ToolSystem plugin-style tool registry |
| 2 | Task 2 | Basic file tools (refactored to use ToolSystem) |
| 3 | Task 3 | InteractiveAgent core class |
| 4 | Task 4 | test_tools.py - test framework |
| 5 | Task 5 | git_tools.py - Git toolset |
| 6 | Task 6 | Integration tests |
| 7 | Task 7 | main.py entry point update |

---

## Expected Outcome

When done, CookieRookie will have:
- ✅ Plugin-style tool system
- ✅ Interactive confirmation mechanism (/confirm /reject /edit)
- ✅ Test execution and generation
- ✅ Git operations
- ✅ Backward compatibility (Debug Agent mode remains available)
