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
    if tool_name == "git_commit":
        files = args.get("files")
        files = [files] if isinstance(files, str) else files
        staged = ", ".join(files) if files else "all changes (git add .)"
        return f"Commit {staged} with the message:\n{_prefixed('  ', args.get('message', ''))}"
    if tool_name == "git_checkout":
        verb = "Create and switch to" if args.get("create") else "Switch to"
        return f"{verb} branch {args.get('branch', '')}"
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


def show_reply(response: dict, thought: str, summary: str) -> None:
    """Print what the model said. Its raw text is shown only when it isn't the thought or the
    summary, as with a reply in the text format."""
    raw = response.get("raw") or ""
    if raw and raw.strip() not in (thought, summary):
        print(f"Raw response:\n{raw[:500]}")
    if thought:
        print(f"Thought: {thought}")


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


SYSTEM_PROMPT = """You are CookieRookie, a debugging agent. Find and fix the bug the user reports in the project in the current directory, using the tools you are given.

## How to work
1. Read the bug report. Find the code involved with find_files and search_files, and read it with read_file.
2. Fix it with the smallest change that works: edit_file for existing files, write_file for new ones.
3. Check the fix, for example by running the code or its tests with exec.
4. When the bug is fixed, or you can't get further, reply without calling a tool: say what was wrong and what you changed. That reply ends the run.

## Rules
- Call one tool per reply, and say in a sentence or two why before the call.
- The user is asked before each edit and command and can decline. If they do, the history shows it, often with what to do instead. Follow that, and don't try the same action again.
- Don't repeat a step that is already in the history.
- To change a line, read the file first and give its line number to edit_file.
- Write your replies in the language of the bug report."""


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

            # 2. 解析 action
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            # 调试：打印原始响应 (with a tool call, the reply's text is the thought, shown below)
            show_reply(response, reasoning, summary)
            
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
            "system": SYSTEM_PROMPT,
            # Only the tools debug mode runs (not the test tools)
            "tools": tool_system.api_tools(list(self.tools)),
        }


def create_agent(llm_client, max_iterations: int = 50, ask=None) -> DebugAgent:
    """创建 Debug Agent"""
    return DebugAgent(llm_client, max_iterations, ask)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50) -> 'InteractiveAgent':
    """创建 Interactive Agent"""
    return InteractiveAgent(llm_client, tool_system, max_iterations)


PLAN_HINT = "/confirm to run it | /skip N to leave out step N | /reject [what to change]"

NO_PLAN = "No plan. Make one with /plan <task>."


class InteractiveAgent:
    """Interactive Agent - 支持用户确认的 Agent"""

    SYSTEM_PROMPT = """You are CookieRookie, a coding agent. Do what the user asks in the project in the current directory, using the tools you are given.

## Tools
{tool_list}

Tools marked [needs confirmation] change files or run commands. The user sees each such call before it runs, and can allow it, change its arguments or decline it.

## How to work
- Call one tool per reply, and say in a sentence or two why before the call.
- Look before you change: find files with find_files or search_files instead of guessing paths, and read a file before you edit it.
- If the user declines an action, the history shows it, often with what to do instead. Follow that, and don't try the same action again.
- Don't repeat a step that is already in the history.
- When the task is done, or you can't get further, reply without calling a tool: say in a few sentences what you did. That reply ends the task.
- Write your replies in the language the user writes in.

## Writing tests
1. Call test_generate with the source file to get its content, the path for the test file and hints for the framework.
2. Write the tests with write_file.
3. Run them with test_run, and fix what fails.

## Plans
When you are asked for a plan, don't call any tool. Reply in exactly this format:

plan: true
summary: the task in one sentence
steps:
  1. [tool_name] what this step does
  2. [tool_name] what this step does
"""

    def __init__(self, llm_client, tool_system, max_iterations: int = 50, project_path: str = None):
        self.llm = llm_client
        self.tool_system = tool_system
        self.max_iterations = max_iterations
        self.pending_action = None
        self.user_modifications = None
        self.project_path = project_path
        # The plan from plan(), until it is run (confirm) or dropped (reject)
        self.current_plan = None

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
            confirm_mark = " [needs confirmation]" if tool_def.confirmable else ""
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
            "system": self._build_system_prompt(),
            "tools": self.tool_system.api_tools(),
        }

        # 自动注入记忆
        if self.memory:
            memory_context = self.memory.get_context()
            context["memory"] = memory_context

        return context

    def confirm(self) -> str:
        """Say yes to what is waiting: the pending edit or command, or else the plan."""
        if self.pending_action:
            return self._run_pending(self.pending_action["tool_args"], "confirmed")
        if self.current_plan:
            return self.execute_plan()
        return "Nothing to confirm."

    def reject(self, new_instructions: str = None) -> str:
        """Say no to what is waiting. For the pending action: with instructions, the agent carries on
        with the same task and reads them as feedback; without, the task stops. For a plan: with
        instructions, the model changes the plan as they say; without, the plan is dropped."""
        if not self.pending_action:
            if not self.current_plan:
                return "Nothing to reject."
            if not new_instructions:
                self.current_plan = None
                return "Plan dropped; nothing ran."
            return self.propose_plan(self.current_plan["task"], new_instructions)

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
            "tools": self.tool_system.api_tools(),
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
        """The plan as the user sees it, with how to answer"""
        summary = plan.get("summary", "")
        lines = [f"Plan: {summary}" if summary else "Plan:", ""]

        # Before (kept for comparison): the title was "## 执行计划", steps that ask first were marked
        # "✅ 需要确认", and it ended with "确认执行？ (/confirm /reject /skip N)"
        steps = plan.get("steps", [])
        if not steps:
            lines.append("(no steps)")
            return "\n".join(lines)

        for step in steps:
            line = f"{step.get('step', '?')}. [{step.get('tool', '?')}] {step.get('description', '')}"
            if step.get("skipped"):
                line += "  (skipped)"
            elif step.get("confirmable"):
                line += "  (asks you first)"
            lines.append(line)

        lines.append("")
        lines.append(PLAN_HINT)

        return "\n".join(lines)

    @staticmethod
    def _plan_steps(steps: list) -> str:
        """The steps of a plan as the model reads them"""
        return "\n".join(
            f"{step['step']}. [{step['tool']}] {step['description']}"
            + (" (the user skipped this step: don't do it)" if step.get("skipped") else "")
            for step in steps)

    def plan(self, task: str, feedback: str = None) -> dict:
        """Ask the model for a plan for task. Nothing runs. With feedback, the model changes the
        current plan as the user asked.

        Returns task, summary and steps (each with step, tool, description and confirmable),
        reply (the model's text), and error if the API call failed. A plan with steps becomes
        the current plan, which confirm() runs.
        """
        request = f"Make a plan for this task, in the plan format:\n\n{task}"
        if feedback and self.current_plan:
            request += (f"\n\nYour last plan was:\n{self._plan_steps(self.current_plan['steps'])}"
                        f"\n\nThe user wants it changed: {feedback}")
        context = {
            "task": request,
            "system": self._build_system_prompt(),
            "history": [],
            "mode": "planning"
        }

        response = self.llm.chat(context)
        if response.get("fatal"):
            return {"task": task, "summary": "", "steps": [], "reply": "", "error": response["error"]}
        plan_text = response.get("raw", "")
        plan = self._parse_plan_response(plan_text)
        plan.update(task=task, reply=plan_text)

        if plan["steps"]:
            self.current_plan = plan
        return plan

    def propose_plan(self, task: str, feedback: str = None) -> str:
        """plan(), as the text to show the user"""
        plan = self.plan(task, feedback)
        if plan.get("error"):
            return f"LLM error: {plan['error']}"
        if not plan["steps"]:
            kept = " The plan from before is still waiting." if self.current_plan else ""
            return (f"The reply had no steps in the plan format, so there is no new plan.{kept} "
                    f"The model said:\n\n{plan['reply'] or '(nothing)'}")
        return self._format_plan(plan)

    def show_plan(self) -> str:
        return self._format_plan(self.current_plan) if self.current_plan else NO_PLAN

    def skip_step(self, step: int) -> str:
        """Leave a step out of the current plan. Returns the plan as it is now, or what is wrong."""
        if not self.current_plan:
            return NO_PLAN
        steps = self.current_plan["steps"]
        if not 1 <= step <= len(steps):
            return f"The plan has no step {step}. Its steps are 1 to {len(steps)}."
        steps[step - 1]["skipped"] = True
        return self._format_plan(self.current_plan)

    def execute_plan(self) -> str:
        """Carry out the current plan, as one task. Edits and commands in it still wait for confirm()."""
        plan, self.current_plan = self.current_plan, None
        if not plan:
            return NO_PLAN
        if all(step.get("skipped") for step in plan["steps"]):
            return "Every step of the plan is skipped, so nothing ran."
        task = (f"{plan['task']}\n\n"
                "The user approved this plan. Carry it out step by step. If what you find shows that "
                "a step is wrong, do what the task needs instead and say why.\n"
                f"{self._plan_steps(plan['steps'])}")
        return self.run(task)

    def _parse_plan_response(self, response: str) -> dict:
        """解析 LLM 的 Plan 响应"""
        result = {
            "summary": "",
            "steps": []
        }

        # 解析 summary
        summary_match = re.search(r'summary:\s*(.+?)(?=\n\W*steps:|$)', response, re.DOTALL | re.IGNORECASE)
        if summary_match:
            result["summary"] = summary_match.group(1).strip().strip("*").strip()

        # 解析 steps
        # Models often add Markdown: "1. **[read_file]** ...", "2) [`exec`] ...", "- 3. [test_run] ..."
        # Before (kept for comparison): re.compile(r'^\s*(\d+)\.\s*\[(\w+)\]\s*(.+?)$', re.MULTILINE)
        step_pattern = re.compile(r'^\s*(?:[-*]\s*)?(\d+)[.)]\s*\**\[\s*`?(\w+)`?\s*\]\**\s*(.+?)\s*$', re.MULTILINE)
        # Numbered in order, so /skip N matches the number shown even if the model's numbers don't
        for step_num, match in enumerate(step_pattern.finditer(response), 1):
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

            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            show_reply(response, reasoning, summary)

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
