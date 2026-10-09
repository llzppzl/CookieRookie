"""
Debug Agent 核心逻辑
"""

import json
import re
from typing import Optional
from .tools import register_tools


SYSTEM_PROMPT = """You are a debugging agent. Your job is to find and fix the bug in the user's code by calling tools.

## How to work
1. Read the bug report
2. Read the code with the tools and find the cause
3. Fix the code
4. Run it to check the fix
5. Repeat until the bug is fixed

## Tools
- read_file(path, offset=1, limit=100): read lines of a file
- edit_file(path, line=N, new_string='new line'): replace line N (preferred)
- edit_file(path, old_string="old text", new_string="new text"): replace text (fails if old_string is not an exact match)
- exec(command, workdir=None, timeout=30): run a shell command
- search_files(pattern, path=".", file_glob="*.py"): search file contents
- find_files(pattern, path="."): find files by name

## Reply format (follow it exactly)

Reply with these lines and **nothing else**:

```
thought: your reasoning (1-2 sentences)
action: tool_name(arg1="value1", arg2="value2")
done: true/false
summary: what you fixed (only when done is true)
```

### Prefer editing by line number

To change code, **use the line number** so the edit does not depend on matching text exactly:

```
# Preferred: replace line 19
action: edit_file(path="user_manager.py", line=19, new_string='    return user["city"]')

# If new_string contains double quotes, wrap it in single quotes
action: edit_file(path="file.py", line=10, new_string='print("hello")')
```

### Example
```
thought: I need to read the file first
action: read_file(path="examples/calculator.py")
done: false

thought: The bug is on line 15
action: edit_file(path="examples/calculator.py", line=15, new_string='    rate = 0.1')
done: false

thought: Fixed; run it to check
action: exec(command="python examples/calculator.py")
done: false
```

## Rules
1. Write the arguments in parentheses right after the tool name
2. **Edit by line number** rather than old_string when you can
3. **If new_string contains double quotes, wrap it in single quotes**
4. When done is true, the action line can be empty
5. Never repeat an action you have already done"""


class DebugAgent:
    def __init__(self, llm_client, max_iterations: int = 10):
        self.llm = llm_client
        self.tools = register_tools()
        self.max_iterations = max_iterations
    
    def run(self, bug_report: str) -> str:
        """运行 agent"""
        context = self._build_initial_context(bug_report)
        
        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")
            
            # 1. LLM 推理
            response = self.llm.chat(context)
            
            # 调试：打印原始响应
            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")
            
            # 2. 解析 action
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")
            
            print(f"Thought: {reasoning}")
            
            if done:
                return summary or "Bug fixed!"
            
            if not action:
                print(f"Warning: No action in response, ending.")
                return f"LLM did not provide action. Response: {response}"
            
            # 3. 执行 action
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            
            if not tool_name:
                return f"Invalid action format: {action}"
            
            if tool_name not in self.tools:
                return f"Unknown tool: {tool_name}"
            
            print(f"Executing: {tool_name}({tool_args})")
            
            tool_func = self.tools[tool_name]
            result = tool_func(**tool_args)
            
            # 打印结果摘要
            result_summary = json.dumps(result, ensure_ascii=False)
            if len(result_summary) > 300:
                result_summary = result_summary[:300] + "..."
            print(f"Result: {result_summary}")
            
            # 4. 更新 context
            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })
        
        return "Max iterations reached"
    
    def _build_initial_context(self, bug_report: str) -> dict:
        """构建初始上下文"""
        return {
            "bug_report": bug_report,
            "history": [],
            "system": SYSTEM_PROMPT
        }


def create_agent(llm_client, max_iterations: int = 50) -> DebugAgent:
    """创建 Debug Agent"""
    return DebugAgent(llm_client, max_iterations)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50) -> 'InteractiveAgent':
    """创建 Interactive Agent"""
    return InteractiveAgent(llm_client, tool_system, max_iterations)


def _describe_args(fn) -> str:
    """The arguments of fn as the model should write them, e.g. "path, offset=1, limit=100"."""
    import inspect
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return "..."
    parts = []
    for p in params:
        if p.kind == p.VAR_POSITIONAL:
            parts.append(f"*{p.name}")
        elif p.kind == p.VAR_KEYWORD:
            parts.append(f"**{p.name}")
        elif p.default is p.empty:
            parts.append(p.name)
        else:
            parts.append(f"{p.name}={p.default!r}")
    return ", ".join(parts)


class InteractiveAgent:
    """Interactive Agent - 支持用户确认的 Agent"""

    SYSTEM_PROMPT = """You are an interactive coding agent. Your job is to complete the user's coding request by calling tools.

## How to work
1. Understand the request
2. Work out the steps
3. Carry them out with the tools
4. Tools marked [asks the user first] (changing files, running commands) wait until the user approves them

## Tools
{tool_list}

## Writing tests
When the user asks for tests:

1. Call `test_generate(source="path/to/source.py")` to get the source code and the test file path
2. Read the returned `source_content` and `framework_hint`
3. Call `write_file(path="path/to/test_file.py", content="the complete test code")` to write the tests
4. Call `test_run()` to check that they pass

## Reply format (follow it exactly)

Reply with these lines and **nothing else**:

```
thought: your reasoning (1-2 sentences)
action: tool_name(arg1="value1", arg2="value2")
done: true/false
summary: what you did (only when done is true)
```

## Rules
1. Write the arguments in parentheses right after the tool name, using the argument names listed above
2. A tool marked [asks the user first] runs only after the user approves it
3. When done is true, the action line can be empty
4. To write tests, call test_generate first, then write the test code with write_file

## Plans

When you are asked for a plan, don't call any tool. Reply in this format instead:
```
plan: true
summary: the task in one line
steps:
  1. [tool_name] what this step does
  2. [tool_name] what this step does
  ...
```
"""

    def __init__(self, llm_client, tool_system, max_iterations: int = 50, project_path: str = None):
        self.llm = llm_client
        self.tool_system = tool_system
        self.max_iterations = max_iterations
        self.pending_action = None
        self.user_modifications = None
        self.project_path = project_path

        # 初始化记忆
        if project_path:
            from .memory import ProjectMemory
            from .explorer import auto_detect_structure

            self.memory = ProjectMemory(project_path)
            structure = auto_detect_structure(project_path)
            self.memory.update_structure(structure)
        else:
            self.memory = None

    def _build_tool_list(self) -> str:
        """构建工具列表字符串"""
        tools = self.tool_system.list_tools()
        tool_lines = []
        for name, tool_def in tools.items():
            confirm_mark = " [asks the user first]" if tool_def.confirmable else ""
            desc = tool_def.description or ""
            # With the argument names, so the model does not have to guess them
            tool_lines.append(f"- {name}({_describe_args(tool_def.fn)}){confirm_mark}" + (f": {desc}" if desc else ""))
        return "\n".join(tool_lines)

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        tool_list = self._build_tool_list()
        return self.SYSTEM_PROMPT.format(tool_list=tool_list)

    def run(self, task: str) -> str:
        """运行 agent"""
        context = self._build_initial_context(task)

        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")

            # 1. LLM 推理
            response = self.llm.chat(context)

            # 调试：打印原始响应
            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")

            # 2. 解析 action
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            print(f"Thought: {reasoning}")

            if done:
                return summary or "Task completed!"

            if not action:
                print(f"Warning: No action in response, continuing.")
                continue

            # 3. 解析 action
            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            if not tool_name:
                return f"Invalid action format: {action}"

            tools = self.tool_system.list_tools()

            if tool_name not in tools:
                return f"Unknown tool: {tool_name}"

            tool_def = tools[tool_name]

            # 如果需要确认，设置 pending_action
            if tool_def.confirmable:
                self.pending_action = {
                    "thought": reasoning,
                    "action": action,
                    "tool_name": tool_name,
                    "tool_args": tool_args
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            # 执行工具
            print(f"Executing: {tool_name}({tool_args})")
            result = tool_def.fn(**tool_args)

            # 打印结果摘要
            result_summary = json.dumps(result, ensure_ascii=False)
            if len(result_summary) > 300:
                result_summary = result_summary[:300] + "..."
            print(f"Result: {result_summary}")

            # 4. 更新 context
            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })

        return "Max iterations reached"

    def _build_initial_context(self, task: str) -> dict:
        context = {
            "task": task,
            "history": [],
            "system": self._build_system_prompt()
        }

        # 自动注入记忆
        if self.memory:
            memory_context = self.memory.get_context()
            context["memory"] = memory_context

        return context

    def confirm(self) -> str:
        """用户确认，执行 pending action"""
        if not self.pending_action:
            return "No pending action to confirm"

        action = self.pending_action["action"]
        tool_args = self.pending_action["tool_args"]

        # 执行 pending action
        print(f"Executing confirmed action: {self.pending_action['tool_name']}({tool_args})")
        tools = self.tool_system.list_tools()
        tool_def = tools[self.pending_action["tool_name"]]
        result = tool_def.fn(**tool_args)

        result_summary = json.dumps(result, ensure_ascii=False)
        if len(result_summary) > 300:
            result_summary = result_summary[:300] + "..."
        print(f"Result: {result_summary}")

        # 重新构建 context 继续循环
        context = {
            "task": self.pending_action.get("task", ""),
            "history": self.pending_action.get("history", []),
            "system": self._build_system_prompt()
        }
        context["history"].append({
            "action": action,
            "result": result,
            "thought": self.pending_action["thought"],
            "iteration": "confirmed"
        })

        self.pending_action = None
        return self.run_from_context(context)

    def reject(self, new_instructions: str = None) -> str:
        """用户拒绝，重新规划"""
        if not self.pending_action:
            return "No pending action to reject"

        self.pending_action = None

        if new_instructions:
            return self.run(new_instructions)
        return "Rejected. Provide new instructions to continue."

    def edit_and_confirm(self, modified_args: dict) -> str:
        """用户修改参数后确认"""
        if not self.pending_action:
            return "No pending action to edit"

        action = self.pending_action["action"]
        action["args"] = modified_args

        print(f"Executing modified action: {self.pending_action['tool_name']}({modified_args})")
        tools = self.tool_system.list_tools()
        tool_def = tools[self.pending_action["tool_name"]]
        result = tool_def.fn(**modified_args)

        result_summary = json.dumps(result, ensure_ascii=False)
        if len(result_summary) > 300:
            result_summary = result_summary[:300] + "..."
        print(f"Result: {result_summary}")

        # 重新构建 context 继续循环
        context = {
            "task": self.pending_action.get("task", ""),
            "history": self.pending_action.get("history", []),
            "system": self._build_system_prompt()
        }
        context["history"].append({
            "action": action,
            "result": result,
            "thought": self.pending_action["thought"],
            "iteration": "edit_confirmed"
        })

        self.pending_action = None
        return self.run_from_context(context)

    def _format_plan(self, plan: dict) -> str:
        """格式化 Plan 为可读文本

        Args:
            plan: 包含 steps 和 summary 的字典

        Returns:
            格式化的计划文本
        """
        lines = ["## 执行计划", ""]

        summary = plan.get("summary", "")
        if summary:
            lines.append(f"任务: {summary}")
            lines.append("")

        steps = plan.get("steps", [])
        if not steps:
            lines.append("(无步骤)")
            return "\n".join(lines)

        for step in steps:
            step_num = step.get("step", "?")
            tool = step.get("tool", "?")
            desc = step.get("description", "")
            confirmable = step.get("confirmable", False)

            line = f"{step_num}. [{tool}] {desc}"
            if confirmable:
                line += " ✅ 需要确认"

            lines.append(line)

        lines.append("")
        lines.append("确认执行？ (/confirm /reject /skip N)")

        return "\n".join(lines)

    def plan(self, task: str) -> dict:
        """让 LLM 生成任务的执行计划

        Args:
            task: 用户任务描述

        Returns:
            Plan 字典，包含 steps 和 summary
        """
        context = {
            "task": f"请为以下任务制定执行计划：{task}",
            "system": self._build_system_prompt(),
            "history": [],
            "mode": "planning"
        }

        response = self.llm.chat(context)
        plan_text = response.get("raw", "")
        plan = self._parse_plan_response(plan_text)

        return plan

    def _parse_plan_response(self, response: str) -> dict:
        """解析 LLM 的 Plan 响应"""
        result = {
            "summary": "",
            "steps": []
        }

        # 解析 summary
        summary_match = re.search(r'summary:\s*(.+?)(?=\nsteps:|$)', response, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()

        # 解析 steps
        step_pattern = re.compile(r'^\s*(\d+)\.\s*\[(\w+)\]\s*(.+?)$', re.MULTILINE)
        for match in step_pattern.finditer(response):
            step_num = int(match.group(1))
            tool_name = match.group(2)
            description = match.group(3).strip()

            confirmable = self.tool_system.is_confirmable(tool_name)

            result["steps"].append({
                "step": step_num,
                "tool": tool_name,
                "description": description,
                "confirmable": confirmable
            })

        return result

    def _show_pending_action(self):
        """打印待确认的 action 供用户决策"""
        reasoning = self.pending_action.get("thought", "")
        tool_name = self.pending_action.get("tool_name", "")
        tool_args = self.pending_action.get("tool_args", {})

        print("\n" + "=" * 50)
        print("Waiting for your approval:")
        print(f"  Thought: {reasoning}")
        print(f"  Action: {tool_name}")
        for k, v in tool_args.items():
            print(f"    {k}: {v}")
        print("=" * 50)
        print("Options: /confirm to run it | /reject to refuse | /edit key=value to change an argument and run it")
        print("=" * 50 + "\n")

    def run_from_context(self, context: dict) -> str:
        """从给定 context 继续运行（内部使用）"""
        task = context.get("task", "")

        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")

            # LLM 推理
            response = self.llm.chat(context)

            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")

            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            print(f"Thought: {reasoning}")

            if done:
                return summary or "Task completed!"

            if not action:
                print(f"Warning: No action in response, continuing.")
                continue

            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            if not tool_name:
                return f"Invalid action format: {action}"

            tools = self.tool_system.list_tools()

            if tool_name not in tools:
                return f"Unknown tool: {tool_name}"

            tool_def = tools[tool_name]

            if tool_def.confirmable:
                self.pending_action = {
                    "thought": reasoning,
                    "action": action,
                    "tool_name": tool_name,
                    "tool_args": tool_args
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            print(f"Executing: {tool_name}({tool_args})")
            result = tool_def.fn(**tool_args)

            result_summary = json.dumps(result, ensure_ascii=False)
            if len(result_summary) > 300:
                result_summary = result_summary[:300] + "..."
            print(f"Result: {result_summary}")

            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })

        return "Max iterations reached"
