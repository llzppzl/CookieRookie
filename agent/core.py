"""
Debug Agent core logic
"""

import json
import os
import re
from typing import Optional
from .tools import register_tools
from .tool_system import tool_system


# ========== Debug mode: ask before risky actions ==========

PREVIEW_LINES = 20


def run_tool(fn, args: dict) -> dict:
    """Run a tool. If it raises (for example on an argument the model made up), the model gets
    the error as the result and can fix its call, instead of the whole run crashing."""
    try:
        return fn(**args)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def declined(reason: str = "") -> dict:
    """The result the model sees when the user declines an edit or command."""
    error = "The user declined this action."
    if reason:
        error += f" They said: {reason}"
    return {"success": False, "error": error}


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
    if tool_name == "test_run":
        from .test_tools import describe_test_run
        known = {k: args[k] for k in ("path", "pattern", "framework") if k in args}
        return describe_test_run(**known)
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
    """Run every edit and command without asking (python main.py --yes "bug")."""
    return "yes", ""


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


def unknown_tool_result(tool_name: str, available) -> dict:
    """The result the model sees when it calls a tool that does not exist."""
    return {
        "success": False,
        "error": f"Unknown tool '{tool_name}'. Use one of: {', '.join(sorted(available))}"
    }


# Replies in a row without an action the agent can run, before it gives up on the task
MAX_REPLIES_WITHOUT_ACTION = 3


def no_action_step(response: dict, iteration) -> dict:
    """The history step for a reply that had no action in the reply format. Without it the model
    got the same request again, usually wrote the same reply, and every iteration was an API call
    that changed nothing."""
    reply = (response.get("raw") or "").strip()
    error = ("Your last reply had no action in the reply format, so nothing ran. Reply again with "
             "the thought:, action: and done: lines, like action: read_file(path=\"app.py\"), "
             "or with done: true and a summary if the task is finished.")
    if reply:
        error += f" Your reply began: {reply[:200]}"
    return {
        "action": {},
        "result": {"success": False, "error": error},
        "thought": response.get("thought", ""),
        "iteration": iteration
    }


def gave_up_without_action(response: dict) -> str:
    """What the user sees when the model kept replying without an action."""
    return (f"Stopped: {MAX_REPLIES_WITHOUT_ACTION} replies in a row had no action in the reply format. "
            f"The last one was:\n{(response.get('raw') or '').strip() or '(empty)'}")


class DebugAgent:
    def __init__(self, llm_client, max_iterations: int = 10, ask=None):
        """ask(tool_name, args) decides on each edit and command before it runs and returns
        (answer, reason), like ask_in_terminal (the default). Pass approve_all to never ask."""
        self.llm = llm_client
        self.tools = register_tools()
        self.max_iterations = max_iterations
        self.ask = ask or ask_in_terminal

    def run(self, bug_report: str) -> str:
        """Run the agent"""
        context = self._build_initial_context(bug_report)
        replies_without_action = 0

        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")
            
            # 1. Ask the LLM
            response = self.llm.chat(context)
            
            # Debugging: print the raw reply
            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")
            
            # 2. Parse the action
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")
            
            print(f"Thought: {reasoning}")
            
            if done:
                return summary or "Bug fixed!"

            # API errors (wrong key, no quota) and cut-off replies won't get better by retrying
            if response.get("fatal"):
                return f"LLM error: {response['error']}"
            
            # A reply in the wrong format: tell the model what was wrong and let it answer again
            if not action:
                replies_without_action += 1
                if replies_without_action >= MAX_REPLIES_WITHOUT_ACTION:
                    return gave_up_without_action(response)
                print("Warning: No action in the reply; asking the model to use the reply format.")
                context["history"].append(no_action_step(response, i + 1))
                continue
            replies_without_action = 0

            # 3. Run the action
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            
            if not tool_name:
                return f"Invalid action format: {action}"
            
            if tool_name not in self.tools:
                # A made-up or misspelled tool name: tell the model and let it pick a real tool
                print(f"Unknown tool: {tool_name}")
                context["history"].append({
                    "action": action,
                    "result": unknown_tool_result(tool_name, self.tools),
                    "thought": reasoning,
                    "iteration": i + 1
                })
                continue
            
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

            # 打印结果摘要
            result_summary = json.dumps(result, ensure_ascii=False)
            if len(result_summary) > 300:
                result_summary = result_summary[:300] + "..."
            print(f"Result: {result_summary}")
            
            # 4. Update the context
            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })
        
        return "Max iterations reached"
    
    def _build_initial_context(self, bug_report: str) -> dict:
        """Build the first context"""
        return {
            "bug_report": bug_report,
            "history": [],
            "system": SYSTEM_PROMPT
        }


def create_agent(llm_client, max_iterations: int = 50, ask=None) -> DebugAgent:
    """创建 Debug Agent"""
    return DebugAgent(llm_client, max_iterations, ask)


def create_interactive_agent(llm_client, tool_system, max_iterations: int = 50,
                             project_path: str = None) -> 'InteractiveAgent':
    """Create an InteractiveAgent. With project_path, it keeps project memory for that folder."""
    return InteractiveAgent(llm_client, tool_system, max_iterations, project_path=project_path)


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
        # The plan from plan(), until it is run (execute_plan) or dropped
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
        """Build the tool list text"""
        tools = self.tool_system.list_tools()
        tool_lines = []
        for name, tool_def in tools.items():
            confirm_mark = " [asks the user first]" if tool_def.confirmable else ""
            desc = tool_def.description or ""
            # With the argument names, so the model does not have to guess them
            tool_lines.append(f"- {name}({_describe_args(tool_def.fn)}){confirm_mark}" + (f": {desc}" if desc else ""))
        return "\n".join(tool_lines)

    def _build_system_prompt(self) -> str:
        """Build the system prompt"""
        tool_list = self._build_tool_list()
        return self.SYSTEM_PROMPT.format(tool_list=tool_list)

    def run(self, task: str) -> str:
        """Run the agent"""
        return self.run_from_context(self._build_initial_context(task))

    def _build_initial_context(self, task: str) -> dict:
        context = {
            "task": task,
            "history": [],
            "system": self._build_system_prompt(),
            # Model replies used so far; max_iterations is the limit for the whole task
            "steps": 0,
        }

        # Add the project memory automatically
        if self.memory:
            memory_context = self.memory.get_context()
            context["memory"] = memory_context

        return context

    def confirm(self) -> str:
        """The user confirmed: run the pending action"""
        if not self.pending_action:
            return "No pending action to confirm"

        tool_args = self.pending_action["tool_args"]

        # Run the pending action
        print(f"Executing confirmed action: {self.pending_action['tool_name']}({tool_args})")
        tools = self.tool_system.list_tools()
        tool_def = tools[self.pending_action["tool_name"]]
        result = tool_def.fn(**tool_args)

        result_summary = json.dumps(result, ensure_ascii=False)
        if len(result_summary) > 300:
            result_summary = result_summary[:300] + "..."
        print(f"Result: {result_summary}")

        context = self._resume_context(self.pending_action, result)
        self.pending_action = None
        return self.run_from_context(context)

    def _resume_context(self, pending: dict, result: dict) -> dict:
        """The context to go on with after the user answered a pending action: its task, its
        history plus the action's result, and the steps already used. Before, the count started
        again from 0, so every /confirm gave the task another max_iterations replies and the
        history showed "Step 1" again after each one."""
        context = {
            "task": pending.get("task", ""),
            "history": pending.get("history", []),
            "system": self._build_system_prompt(),
            "memory": pending.get("memory"),
            "steps": pending.get("steps", 0),
        }
        context["history"].append({
            "action": pending["action"],
            "result": result,
            "thought": pending["thought"],
            "iteration": pending.get("steps") or "confirmed"
        })
        return context

    def reject(self, new_instructions: str = None) -> str:
        """Don't run the pending action. With instructions, the model hears why and goes on with
        the same task; without, the task stops."""
        if not self.pending_action:
            return "No pending action to reject"

        pending, self.pending_action = self.pending_action, None
        if not new_instructions:
            return "Rejected. Provide new instructions to continue."

        # Before: run(new_instructions) started a new task made of only the reason, so the agent
        # forgot what it was doing and everything it had read so far
        return self.run_from_context(self._resume_context(pending, declined(new_instructions)))

    @staticmethod
    def _coerce_args(fn, args: dict) -> dict:
        """Turn values typed in /edit, which are always text, into the types the tool takes
        (line=19 becomes 19, use_regex=true becomes True). Raises ValueError for an argument the
        tool doesn't have or a value of the wrong type."""
        import inspect
        import typing

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
            # The type from the annotation (Optional[int] counts as int), else from the default
            expected = param.annotation
            if typing.get_origin(expected) is typing.Union:
                options = [a for a in typing.get_args(expected) if a is not type(None)]
                expected = options[0] if len(options) == 1 else None
            if expected not in (int, float, bool):
                expected = type(param.default) if type(param.default) in (int, float, bool) else None
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

    def edit_and_confirm(self, modified_args: dict) -> str:
        """Change some arguments of the pending action, then run it. Arguments not given keep
        their values. A bad argument runs nothing and leaves the action pending."""
        if not self.pending_action:
            return "No pending action to edit"

        tools = self.tool_system.list_tools()
        tool_def = tools[self.pending_action["tool_name"]]
        try:
            changes = self._coerce_args(tool_def.fn, modified_args)
        except ValueError as e:
            return f"Nothing ran: {e}. The action is still waiting (/confirm, /reject or /edit again)."
        # Before (kept for comparison): the typed arguments replaced all of them, so /edit line=19
        # dropped path and new_string, and passed "19" as text
        modified_args = {**self.pending_action["tool_args"], **changes}

        action = self.pending_action["action"]
        action["args"] = modified_args

        print(f"Executing modified action: {self.pending_action['tool_name']}({modified_args})")
        result = tool_def.fn(**modified_args)

        result_summary = json.dumps(result, ensure_ascii=False)
        if len(result_summary) > 300:
            result_summary = result_summary[:300] + "..."
        print(f"Result: {result_summary}")

        context = self._resume_context(self.pending_action, result)
        self.pending_action = None
        return self.run_from_context(context)

    PLAN_HINT = "/confirm to run it | /skip N to leave out step N | /reject [what to change]"
    NO_PLAN = "No plan. Make one with /plan <task>."

    def _format_plan(self, plan: dict) -> str:
        """The plan as the user sees it, with how to answer"""
        summary = plan.get("summary", "")
        lines = [f"Plan: {summary}" if summary else "Plan:", ""]

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
        lines.append(self.PLAN_HINT)
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

        Returns task, summary and steps (each with step, tool, description and confirmable), reply
        (the model's text) and error (if the API call failed). A plan with steps becomes the
        current plan, which execute_plan() runs.
        """
        request = ("Make a plan for this task. Don't call any tool yet: reply only in the plan format "
                   "(plan: true, summary: one line, steps: numbered lines like \"1. [tool_name] what to do\").\n\n"
                   f"Task: {task}")
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
        plan_text = response.get("raw", "") or ""
        plan = self._parse_plan_response(plan_text)
        error = response.get("error") or ""
        plan.update(task=task, reply=plan_text, error=error if error.startswith("API error") else "")
        if plan["steps"]:
            self.current_plan = plan
        return plan

    def propose_plan(self, task: str, feedback: str = None) -> str:
        """plan(), as the text to show the user"""
        plan = self.plan(task, feedback)
        if plan["steps"]:
            return self._format_plan(plan)
        if plan.get("error"):
            return f"LLM error: {plan['error']}"
        kept = " The plan from before is still waiting." if self.current_plan else ""
        return (f"The reply had no steps in the plan format, so there is no new plan.{kept} "
                f"The model said:\n\n{plan['reply'] or '(nothing)'}")

    def show_plan(self) -> str:
        return self._format_plan(self.current_plan) if self.current_plan else self.NO_PLAN

    def skip_step(self, step: int) -> str:
        """Leave a step out of the current plan. Returns the plan as it is now, or what is wrong."""
        if not self.current_plan:
            return self.NO_PLAN
        steps = self.current_plan["steps"]
        if not 1 <= step <= len(steps):
            return f"The plan has no step {step}. Its steps are 1 to {len(steps)}."
        steps[step - 1]["skipped"] = True
        return self._format_plan(self.current_plan)

    def drop_plan(self) -> str:
        self.current_plan = None
        return "Plan dropped; nothing ran."

    def execute_plan(self, plan: dict = None) -> str:
        """Carry out a plan (the current one by default) as one task. Edits and commands in it
        still wait for /confirm."""
        plan = plan or self.current_plan
        self.current_plan = None
        if not plan:
            return self.NO_PLAN
        if all(step.get("skipped") for step in plan["steps"]):
            return "Every step of the plan is skipped, so nothing ran."
        task = (f"{plan.get('task') or plan.get('summary', '')}\n\n"
                "The user approved this plan. Carry it out step by step. If what you find shows that "
                "a step is wrong, do what the task needs instead and say why.\n"
                f"{self._plan_steps(plan['steps'])}")
        return self.run(task)

    def _parse_plan_response(self, response: str) -> dict:
        """Read a plan out of the model's reply"""
        result = {
            "summary": "",
            "steps": []
        }

        summary_match = re.search(r'summary:\s*(.+?)(?=\n\W*steps:|$)', response, re.DOTALL | re.IGNORECASE)
        if summary_match:
            result["summary"] = summary_match.group(1).strip().strip("*").strip()

        # Models often add Markdown: "1. **[read_file]** ...", "2) [`exec`] ...", "- 3. [test_run] ..."
        step_pattern = re.compile(r'^\s*(?:[-*]\s*)?(\d+)[.)]\s*\**\[\s*`?(\w+)`?\s*\]\**\s*(.+?)\s*$', re.MULTILINE)
        # Numbered in order, so /skip N matches the number shown even if the model's numbers don't
        for step_num, match in enumerate(step_pattern.finditer(response), 1):
            tool_name = match.group(2)
            result["steps"].append({
                "step": step_num,
                "tool": tool_name,
                "description": match.group(3).strip(),
                "confirmable": self.tool_system.is_confirmable(tool_name)
            })

        return result

    def _show_pending_action(self):
        """Print the pending action so the user can decide"""
        reasoning = self.pending_action.get("thought", "")
        tool_name = self.pending_action.get("tool_name", "")
        tool_args = self.pending_action.get("tool_args", {})

        print("\n" + "=" * 50)
        print("Waiting for your approval:")
        print(f"  Thought: {reasoning}")
        # The same preview as debug mode: the lines an edit changes, the start of a file it writes,
        # the command it runs. The raw arguments put a whole file on one line and hid the old text
        print(preview_action(tool_name, tool_args))
        print("=" * 50)
        print("Options: /confirm to run it | /reject to refuse | /edit key=value to change an argument and run it")
        print("=" * 50 + "\n")

    def run_from_context(self, context: dict) -> str:
        """Continue running from the given context (internal)"""
        replies_without_action = 0
        context.setdefault("steps", 0)

        while context["steps"] < self.max_iterations:
            context["steps"] += 1
            # The step number, counted over the whole task (across /confirm, /reject and /edit)
            i = context["steps"] - 1
            print(f"\n=== Iteration {i + 1} ===")

            # Ask the LLM
            response = self.llm.chat(context)

            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")

            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")

            print(f"Thought: {reasoning}")

            if done:
                return summary or "Task completed!"

            # API errors (wrong key, no quota) and cut-off replies won't get better by retrying.
            # A reply that just isn't in the expected format is retried: the next one may be fine
            if response.get("fatal"):
                return f"LLM error: {response['error']}"

            # Tell the model what was wrong, so the next reply can be different
            if not action:
                replies_without_action += 1
                if replies_without_action >= MAX_REPLIES_WITHOUT_ACTION:
                    return gave_up_without_action(response)
                print("Warning: No action in the reply; asking the model to use the reply format.")
                context["history"].append(no_action_step(response, i + 1))
                continue
            replies_without_action = 0

            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            if not tool_name:
                return f"Invalid action format: {action}"

            tools = self.tool_system.list_tools()

            if tool_name not in tools:
                # A made-up or misspelled tool name: tell the model and let it pick a real tool
                print(f"Unknown tool: {tool_name}")
                context["history"].append({
                    "action": action,
                    "result": unknown_tool_result(tool_name, tools),
                    "thought": reasoning,
                    "iteration": i + 1
                })
                continue

            tool_def = tools[tool_name]

            if tool_def.confirmable:
                self.pending_action = {
                    "thought": reasoning,
                    "action": action,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    # Keep the task, history and step count so /confirm continues from here
                    # instead of starting over
                    "task": context.get("task", ""),
                    "history": context["history"],
                    "memory": context.get("memory"),
                    "steps": context["steps"],
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
