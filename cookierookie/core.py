"""
Debug Agent 核心逻辑
"""

import inspect
import json
import os
import re
import typing
from typing import Optional
from .tools import register_tools
from .tool_system import tool_system


# ========== Running tools and asking before risky ones ==========

PREVIEW_LINES = 20


def run_tool(fn, args: dict) -> dict:
    """Run a tool. If it raises (for example on an argument the model made up), the model gets
    the error as the result and can fix its call; the session keeps going."""
    try:
        return fn(**args)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def declined(reason: str = "") -> dict:
    """The result the model sees when the user says no to an edit or command."""
    error = "The user declined this action."
    if reason:
        error += f" They said: {reason}"
    return {"success": False, "error": error}


def print_result(result) -> None:
    summary = json.dumps(result, ensure_ascii=False, default=str)
    if len(summary) > 300:
        summary = summary[:300] + "..."
    print(f"Result: {summary}")


def _prefixed(prefix: str, text) -> str:
    lines = str(text).splitlines() or [""]
    shown = [prefix + line for line in lines[:PREVIEW_LINES]]
    if len(lines) > PREVIEW_LINES:
        shown.append(f"  ... {len(lines) - PREVIEW_LINES} more lines")
    return "\n".join(shown)


def _line_of(path: str, line) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        return lines[int(line) - 1] if int(line) >= 1 else None
    except (OSError, ValueError, IndexError):
        return None


def preview_action(tool_name: str, args: dict) -> str:
    """Show what an edit or command will do, so the user can decide before it runs."""
    path = args.get("path", "")
    if tool_name == "exec":
        details = ", ".join(f"{k}={args[k]}" for k in ("workdir", "timeout") if args.get(k))
        return f"Run command{' (' + details + ')' if details else ''}:\n  {args.get('command', '')}"
    if tool_name == "edit_file" and args.get("line") is not None:
        old = _line_of(path, args["line"])
        before = _prefixed("- ", old) if old is not None else "  (this line does not exist)"
        return f"Edit {path}, line {args['line']}:\n{before}\n{_prefixed('+ ', args.get('new_string', ''))}"
    if tool_name == "edit_file":
        return (f"Edit {path}:\n{_prefixed('- ', args.get('old_string', ''))}\n"
                f"{_prefixed('+ ', args.get('new_string', ''))}")
    if tool_name == "write_file":
        content = str(args.get("content", ""))
        verb = "Overwrite" if os.path.exists(path) else "Create"
        return f"{verb} {path} ({len(content.splitlines())} lines):\n{_prefixed('+ ', content)}"
    return f"{tool_name}(" + ", ".join(f"{k}={v!r}" for k, v in args.items()) + ")"


def ask_in_terminal(tool_name: str, args: dict):
    """Show an edit or command and ask whether to run it.

    Returns (answer, reason): answer is "yes", "all" (yes to this and everything after it),
    "no" or "quit". Anything typed other than y, a or q declines, and is passed to the model.
    """
    print("\n" + preview_action(tool_name, args))
    try:
        reply = input("Allow? [y]es / [N]o / [a]ll / [q]uit, or tell the agent what to do instead: ").strip()
    except EOFError:
        return "quit", ("there is no terminal to ask in. Run it in a terminal, "
                        "or pass --yes to allow edits and commands without asking")
    word = reply.lower()
    if word in ("y", "yes"):
        return "yes", ""
    if word in ("a", "all"):
        return "all", ""
    if word in ("q", "quit"):
        return "quit", ""
    if word in ("", "n", "no"):
        return "no", ""
    return "no", reply


def approve_all(tool_name: str, args: dict):
    """Run every edit and command without asking (cookierookie --yes)."""
    return "yes", ""


def _expected_type(param):
    annotation = param.annotation
    if typing.get_origin(annotation) is typing.Union:  # Optional[int]
        options = [a for a in typing.get_args(annotation) if a is not type(None)]
        annotation = options[0] if len(options) == 1 else None
    if annotation in (int, float, bool):
        return annotation
    if type(param.default) in (int, float, bool):
        return type(param.default)
    return None


def coerce_args(fn, args: dict) -> dict:
    """Turn values typed in /edit, which are always text, into the types the tool takes
    (line=19 becomes 19). Raises ValueError for a name the tool doesn't have or a bad value."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return dict(args)
    takes_any = any(p.kind == p.VAR_KEYWORD for p in params.values())
    coerced = {}
    for key, value in args.items():
        param = params.get(key)
        if param is None:
            if not takes_any:
                raise ValueError(f"{key!r} is not an argument of this tool. It takes: {', '.join(params)}")
            coerced[key] = value
            continue
        expected = _expected_type(param)
        if not isinstance(value, str) or expected is None:
            coerced[key] = value
        elif expected is bool:
            if value.lower() not in ("true", "false"):
                raise ValueError(f"{key} must be true or false, not {value!r}")
            coerced[key] = value.lower() == "true"
        else:
            try:
                coerced[key] = expected(value)
            except ValueError:
                raise ValueError(f"{key} must be a number, not {value!r}") from None
    return coerced


SYSTEM_PROMPT = """你是一个 Debug Agent。你的任务是通过工具自动定位并修复代码中的 bug。

## 工作流程
1. 分析用户提供的 bug 报告
2. 使用工具读取代码，分析错误
3. 修复代码
4. 运行验证
5. 重复直到 bug 修复

## 可用工具
- read_file(path, offset=1, limit=100): 读取文件
- edit_file(path, line=行号, new_string='新内容'): 按行号修改（推荐）
- edit_file(path, old_string="旧内容", new_string="新内容"): 字符串替换（容易出错）
- exec(command, workdir=None, timeout=30): 执行命令
- search_files(pattern, path=".", file_glob="*.py"): 搜索关键词
- find_files(pattern, path="."): 查找文件

## 输出格式（必须严格遵守！）

严格按照这个格式输出，**不要有任何其他内容**：

```
thought: 你的推理过程（1-2句话）
action: 工具名(参数1="值1", 参数2="值2")
done: true/false
summary: 修复总结（仅当done=true时）
```

### 重要：优先使用行号模式！

当需要修改代码时，**优先使用行号模式**，避免字符串匹配问题：

```
# 推荐（按行号修改）
action: edit_file(path="user_manager.py", line=19, new_string='    return user["city"]')

# 注意：如果 new_string 内部包含双引号，请用单引号包裹整个字符串！
action: edit_file(path="file.py", line=10, new_string='print("hello")')
```

### 示例
```
thought: 需要先读取文件查看代码内容
action: read_file(path="examples/calculator.py")
done: false

thought: 发现bug在第15行，需要修改
action: edit_file(path="examples/calculator.py", line=15, new_string='    rate = 0.1')
done: false

thought: 已修复，需要验证运行结果
action: exec(command="python examples/calculator.py")
done: false
```

## 重要规则
1. action 后面必须紧跟括号和参数
2. **修改代码时尽量用 line 模式**，不要用 old_string
3. **new_string 如果包含双引号，请用单引号包裹！**
4. 如果 done=true，action 那一行可以为空
5. 绝对不要重复已经做过的操作！"""


class DebugAgent:
    def __init__(self, llm_client, max_iterations: int = 10, ask=None):
        """ask(tool_name, args) decides on each edit and command before it runs and returns
        (answer, reason), like ask_in_terminal (the default). Pass approve_all to never ask."""
        self.llm = llm_client
        self.tools = register_tools()
        self.max_iterations = max_iterations
        self.ask = ask or ask_in_terminal

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
            
            if response.get("fatal"):
                return f"LLM error: {response['error']}"

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

            # Edits and commands run only if the user says yes
            answer, reason = "yes", ""
            if tool_system.is_confirmable(tool_name):
                answer, reason = self.ask(tool_name, tool_args)
                if answer == "quit":
                    return f"Stopped before {tool_name}" + (f": {reason}." if reason else " (it did not run).")
                if answer == "all":
                    print("Allowing every edit and command for the rest of this run.")
                    self.ask = approve_all

            if answer == "no":
                print(f"Skipped: {tool_name}")
                result = declined(reason)
            else:
                print(f"Executing: {tool_name}({tool_args})")
                result = run_tool(self.tools[tool_name], tool_args)
            print_result(result)

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


def create_agent(llm_client, max_iterations: int = 50, ask=None) -> DebugAgent:
    """创建 Debug Agent"""
    return DebugAgent(llm_client, max_iterations, ask)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50) -> 'InteractiveAgent':
    """创建 Interactive Agent"""
    return InteractiveAgent(llm_client, tool_system, max_iterations)


class InteractiveAgent:
    """Interactive Agent - 支持用户确认的 Agent"""

    SYSTEM_PROMPT = """你是一个 Interactive Coding Agent。你的任务是通过工具自动完成用户的编码请求。

## 工作流程
1. 分析用户请求
2. 规划执行步骤
3. 使用工具执行任务
4. 对于危险操作（修改文件、执行命令等），系统会要求确认

## 可用工具
{tool_list}

## 测试生成流程 (TDD)
当用户要求生成测试时，按以下步骤：

1. 调用 `test_generate(source="源码路径")` 获取源码内容和目标路径
2. 分析返回的 `source_content` 和 `framework_hint`
3. 调用 `write_file(path=目标路径, content="完整的测试代码")` 写入生成的测试
4. 调用 `test_run()` 验证测试通过

## 输出格式（必须严格遵守！）

严格按照这个格式输出，**不要有任何其他内容**：

```
thought: 你的推理过程（1-2句话）
action: 工具名(参数1="值1", 参数2="值2")
done: true/false
summary: 总结（仅当done=true时）
```

## 重要规则
1. action 后面必须紧跟括号和参数
2. 如果工具标记为 [需要确认]，你需要等待用户确认后才能执行
3. 如果 done=true，action 那一行可以为空
4. 生成测试时，先调用 test_generate 获取源码，再生成测试代码并用 write_file 写入

## 规划模式

当用户输入复杂任务时，先规划再执行：

1. 分析任务需要的步骤
2. 使用 plan(task) 生成执行计划
3. 展示计划给用户确认
4. 用户确认后使用 execute_plan(plan) 执行

## Plan 输出格式

规划时返回：
```
plan: true
summary: 任务总结（一句话）
steps:
  1. [tool_name] 步骤描述
  2. [tool_name] 步骤描述
  ...
```

## 执行格式

执行时返回：
```
thought: 你的推理过程
action: 工具名(参数)
done: true/false
summary: 总结
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
            confirm_mark = " [需要确认]" if tool_def.confirmable else ""
            desc = tool_def.description or ""
            tool_lines.append(f"- {name}{confirm_mark}: {desc}")
        return "\n".join(tool_lines)

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        tool_list = self._build_tool_list()
        return self.SYSTEM_PROMPT.format(tool_list=tool_list)

    def run(self, task: str) -> str:
        """运行 agent"""
        return self.run_from_context(self._build_initial_context(task))

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
        return self._run_pending(self.pending_action["tool_args"], "confirmed")

    def reject(self, new_instructions: str = None) -> str:
        """Decline the pending action. With instructions, the agent carries on with the same task
        and reads them as feedback; without, the task stops."""
        if not self.pending_action:
            return "No pending action to reject"

        pending = self.pending_action
        self.pending_action = None

        if not new_instructions:
            return ("Rejected; nothing ran and the task stopped. "
                    "Next time, /reject <what to do instead> lets the agent try another way.")
        print(f"Skipped: {pending['tool_name']}")
        return self._continue(pending, pending["action"], declined(new_instructions), "rejected")

    def edit_and_confirm(self, modified_args: dict) -> str:
        """Change some arguments of the pending action, then run it. The others keep their values.
        Text values are converted to the types the tool takes, e.g. {"line": "19"} becomes 19."""
        if not self.pending_action:
            return "No pending action to edit"

        tool_def = self.tool_system.list_tools()[self.pending_action["tool_name"]]
        try:
            changes = coerce_args(tool_def.fn, modified_args)
        except ValueError as e:
            return f"Nothing ran: {e}"
        return self._run_pending({**self.pending_action["tool_args"], **changes}, "edit_confirmed")

    def _run_pending(self, tool_args: dict, iteration: str) -> str:
        """Run the pending action with tool_args and carry on with the same task."""
        pending = self.pending_action
        self.pending_action = None

        print(f"Executing: {pending['tool_name']}({tool_args})")
        tool_def = self.tool_system.list_tools()[pending["tool_name"]]
        result = run_tool(tool_def.fn, tool_args)
        print_result(result)

        action = {"tool": pending["tool_name"], "args": tool_args}
        return self._continue(pending, action, result, iteration)

    def _continue(self, pending: dict, action: dict, result: dict, iteration: str) -> str:
        """Go on with the task the pending action came from, with its result in the history."""
        context = {
            "task": pending.get("task", ""),
            "history": pending.get("history", []),
            "system": self._build_system_prompt(),
            "memory": pending.get("memory"),
        }
        context["history"].append({
            "action": action,
            "result": result,
            "thought": pending.get("thought", ""),
            "iteration": iteration
        })
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
        """Show the pending edit or command and how to answer."""
        reasoning = self.pending_action.get("thought", "")

        print("\n" + "=" * 50)
        if reasoning:
            print(f"Thought: {reasoning}\n")
        print(preview_action(self.pending_action.get("tool_name", ""), self.pending_action.get("tool_args", {})))
        print("=" * 50)
        print("/confirm to run it | /reject [what to do instead] | /edit key=value to change it, then run")
        print("=" * 50 + "\n")

    def run_from_context(self, context: dict) -> str:
        """从给定 context 继续运行（内部使用）"""
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

            # API 报错（key 错误、额度不足等）或输出被截断，重试也不会好，停下来告诉用户
            # 格式解析失败不算，模型下一轮可能就输出正确了
            if response.get("fatal"):
                return f"LLM error: {response['error']}"

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
                    "tool_args": tool_args,
                    # 保存任务和历史，确认后从这里继续，而不是从空白开始
                    "task": context.get("task", ""),
                    "history": context["history"],
                    "memory": context.get("memory"),
                }
                self._show_pending_action()
                return "awaiting_confirmation"

            print(f"Executing: {tool_name}({tool_args})")
            result = run_tool(tool_def.fn, tool_args)
            print_result(result)

            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })

        return "Max iterations reached"
