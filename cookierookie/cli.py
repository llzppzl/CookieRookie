"""
CookieRookie 命令行入口
支持多种 LLM 提供商 (Minimax, DeepSeek, Kimi, GLM, Anthropic)

用法：
    cookierookie                      交互模式（在当前目录的项目上工作）
    cookierookie "bug 描述"            Debug 模式
    cookierookie --yes "bug 描述"      Debug 模式，修改文件和执行命令前不再询问
"""

import argparse
import ast
import os
import shlex
import json
import re
from pathlib import Path

import requests

from cookierookie import DebugAgent
from cookierookie.core import approve_all


# 仓库根目录：从源码直接运行时，兼容旧的 <repo>/.env 配置
REPO_DIR = Path(__file__).resolve().parent.parent

# 用户级配置文件，pip 安装后在任意项目里都能用
USER_CONFIG = Path.home() / ".config" / "cookierookie" / ".env"


# 1024 写不下一个中等大小的文件，write_file / test_generate 会被截断
DEFAULT_MAX_TOKENS = 8192


# Users' answers to a pending action, as the model reads them in the history
USER_DECISIONS = {
    "confirmed": " (the user allowed it)",
    "edit_confirmed": " (the user changed the arguments, then allowed it)",
    "rejected": " (the user declined it)",
}

# Long arguments (file content, replacement text) are shortened in the history
ARG_PREVIEW_CHARS = 200


def _show_arg(value) -> str:
    """An argument of an earlier tool call, as the model sees it in the history. Strings are quoted
    and escaped, so quotes and newlines in them stay readable."""
    if not isinstance(value, str):
        return repr(value)
    if len(value) > ARG_PREVIEW_CHARS:
        value = value[:ARG_PREVIEW_CHARS] + f"... [{len(value)} characters in total]"
    return json.dumps(value, ensure_ascii=False)


class LLMClient:
    """通用 LLM 客户端 (Anthropic 兼容模式)"""
    
    def __init__(self, api_key: str, model: str = "MiniMax-M2.5", base_url: str = "https://api.minimax.io/anthropic",
                 max_tokens: int = DEFAULT_MAX_TOKENS):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
    
    def chat(self, context: dict) -> dict:
        """调用 LLM API (Anthropic 兼容格式)

        The tools in context["tools"] are offered through the API's tool use, so a tool call comes
        back as JSON and its arguments (file content with quotes, backslashes, newlines) arrive exactly.
        With tools offered, a reply that calls none is the model's final answer. Replies in the older
        text format (thought: / action: / done:) are still understood.
        """
        messages = [
            {"role": "user", "content": self._build_user_message(context)}
        ]
        
        # 添加 system prompt
        system_prompt = context.get("system", "")
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.7,
            "system": system_prompt
        }
        if context.get("tools"):
            data["tools"] = context["tools"]

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=data,
                timeout=60
            )
        except requests.RequestException as e:
            return {"action": None, "error": f"Could not reach {self.base_url}: {e}", "raw": "", "fatal": True}

        if response.status_code != 200:
            return {"action": None, "error": f"API error: {response.status_code} - {response.text[:500]}",
                    "raw": response.text, "fatal": True}
        
        result = response.json()

        # 输出被 max_tokens 截断时，解析结果不可信（例如 write_file 只写了半个文件），直接报错
        if result.get("stop_reason") == "max_tokens":
            return {
                "action": None,
                "error": f"The model's reply was cut off at max_tokens={self.max_tokens}. "
                         f"Set MAX_TOKENS to a higher value or ask for a smaller change.",
                "raw": "",
                "fatal": True,
            }
        
        # 遍历所有 content blocks
        text_parts = []
        thinking_content = ""
        tool_calls = []

        for block in result.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "thinking":
                thinking_content = block.get("thinking", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(block)
        text = "\n".join(part for part in text_parts if part).strip()

        # 打印 thinking（调试用）
        if thinking_content:
            print(f"\n=== LLM Thinking ===\n{thinking_content[:300]}...\n=====================\n")

        # One tool per step: if the model asked for several, the first one runs and it can ask
        # for the others in its next reply, with this result in front of it
        if tool_calls:
            call = tool_calls[0]
            return {
                "thought": text,
                "action": {"tool": call.get("name"), "args": call.get("input") or {}},
                "done": False,
                "summary": "",
                "raw": text,
            }

        # 解析响应
        parsed = self._parse_response(text)

        if parsed and (parsed["action"] or parsed["done"]):
            parsed["raw"] = text
            return parsed

        if context.get("tools") and text:
            return {"thought": "", "action": {}, "done": True, "summary": text, "raw": text}

        if parsed:
            parsed["raw"] = text
            return parsed

        return {"action": None, "error": f"Failed to parse: {text[:200]}", "raw": text}
    
    def _parse_response(self, content: str) -> dict:
        """解析 LLM 响应 - 支持多种格式"""
        content = content.strip()
        
        result = {
            "thought": "",
            "action": {},
            "done": False,
            "summary": ""
        }
        
        # Labels in any case: a model may copy "Thought:" / "Action:" from the history
        # 提取 thought
        # The thought ends at the next label, which is done: when there is no action
        thought_match = re.search(r'thought:\s*(.+?)(?=\n(?:action|done|summary):|$)', content,
                                  re.DOTALL | re.IGNORECASE)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        # 提取 action
        action_match = re.search(r'action:\s*(.+?)(?=\ndone:|$)', content, re.DOTALL | re.IGNORECASE)
        if action_match:
            action_str = action_match.group(1).strip()
            if action_str:
                # DOTALL: the arguments can span lines (file content)
                func_match = re.match(r'(\w+)\((.*)\)', action_str, re.DOTALL)
                if func_match:
                    tool_name = func_match.group(1)
                    args_str = func_match.group(2)
                    args = self._parse_args(args_str)
                    result["action"] = {"tool": tool_name, "args": args}
        
        # 提取 done
        done_match = re.search(r'done:\s*(true|false)', content, re.IGNORECASE)
        if done_match:
            result["done"] = done_match.group(1).lower() == "true"
        
        # 提取 summary
        summary_match = re.search(r'summary:\s*(.+?)$', content, re.DOTALL | re.IGNORECASE)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()
        
        if not result["thought"] and not result["action"]:
            return None
        
        return result
    
    def _parse_args(self, args_str: str) -> dict:
        """解析工具参数 - 支持多种格式"""
        # The text format looks like a Python call, so read it as one first. That gets quotes inside
        # strings and escapes like \n right. If it isn't valid Python, the patterns below take over.
        try:
            call = ast.parse(f"f({args_str})", mode="eval").body
            if isinstance(call, ast.Call) and call.keywords and not call.args:
                return {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}
        except (SyntaxError, ValueError, TypeError):
            pass

        args = {}
        
        # 数字参数: key=123
        for match in re.finditer(r'(\w+)=(\d+)', args_str):
            args[match.group(1)] = int(match.group(2))
        
        # 双引号字符串: key="value"
        for match in re.finditer(r'(\w+)="((?:[^"\\]|\\.)*)"', args_str):
            key = match.group(1)
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            args[key] = value
        
        # 单引号字符串: key='value'
        for match in re.finditer(r'(\w+)=\'((?:[^\'\\]|\\.)*)\'', args_str):
            key = match.group(1)
            value = match.group(2).replace("\\'", "'").replace('\\\\', '\\')
            args[key] = value
        
        return args
    
    def _build_user_message(self, context: dict) -> str:
        """构建用户消息"""
        parts = []
        
        # Debug 模式传 bug_report，交互模式传 task
        if context.get("bug_report"):
            parts.append(f"## Bug Report\n{context['bug_report']}")
        else:
            parts.append(f"## Task\n{context.get('task', '')}")

        # 项目记忆（交互模式下由 InteractiveAgent 注入）
        if context.get("memory"):
            parts.append("\n" + context["memory"])
        
        # 历史记录
        if context["history"]:
            parts.append("\n## History (what you have done so far)")
            for step, h in enumerate(context["history"], 1):
                action = h.get("action", {})
                result = h.get("result", {})
                thought = h.get("thought", "")
                iteration = h.get("iteration", "?")

                tool_name = action.get("tool", "unknown")
                args = action.get("args", {})

                # Steps are numbered here: iteration restarts after each /confirm, and is
                # "confirmed", "edit_confirmed" or "rejected" for the step the user answered
                parts.append(f"\n### Step {step}{USER_DECISIONS.get(iteration, '')}")
                if thought:
                    parts.append(f" Thought: {thought}")

                if tool_name and tool_name != "unknown":
                    # 原来的写法：new_string 超过 50 字符就整段省略（保留作学习对比）
                    # for k, v in args.items():
                    #     if k == "new_string" and len(str(v)) > 50:
                    #         args_parts.append(f'{k}="[内容截断]"')
                    #     else:
                    #         args_parts.append(f'{k}="{v}"' if isinstance(v, str) else f'{k}={v}')
                    args_str = ", ".join(f"{k}={_show_arg(v)}" for k, v in args.items())
                    parts.append(f" Action: {tool_name}({args_str})")

                # ===== 旧的结果摘要逻辑（保留作学习对比） =====
                # if tool_name == "read_file" and result.get("success"):
                #     parts.append(f" Result: 文件内容已读取")
                # elif tool_name == "exec" and result.get("success"):
                #     stdout = result.get("stdout", "").strip()
                #     if len(stdout) > 100:
                #         stdout = stdout[:100] + "..."
                #     parts.append(f" Result: {stdout}")
                # elif tool_name == "edit_file" and result.get("success"):
                #     parts.append(f" Result: 文件已修改")
                # elif not result.get("success"):
                #     parts.append(f" Result: 失败 - {result.get('error', result.get('stderr', 'unknown'))}")
                # else:
                #     parts.append(f" Result: success")

                # ===== 新的结果摘要逻辑：保留状态 + 关键细节 =====

                # 没有 result 的情况（或者工具返回的不是 dict）
                if not isinstance(result, dict):
                    parts.append(f" Result: {'(nothing returned)' if result is None else result}")
                    continue

                success = result.get("success")

                # 统一的失败分支
                # A failure without an error message (a command or test run that exited with an
                # error) falls through, so the model sees its output and can tell why it failed
                if success is False and result.get("error"):
                    parts.append(f" Result: failed - {result['error']}")
                    continue

                # 按工具类型分别给出「一句话总结 + 关键字段」
                if tool_name == "read_file" and success:
                    lines = result.get("lines", "?")
                    total = result.get("total", "?")
                    content = result.get("content", "")

                    parts.append(f" Result: lines {lines} of {total}.")

                    # 对长文件做截断，但明确标出
                    max_chars = 2000
                    snippet = content
                    truncated = False
                    if len(snippet) > max_chars:
                        snippet = snippet[:max_chars]
                        truncated = True

                    if snippet:
                        parts.append("\n```code\n" + snippet + ("\n... [cut off]" if truncated else "") + "\n```")

                elif tool_name == "exec":
                    returncode = result.get("returncode")
                    stdout = (result.get("stdout") or "").strip()
                    stderr = (result.get("stderr") or "").strip()

                    parts.append(f" Result: the command exited with code {returncode}.")

                    def _truncate(text: str, label: str) -> str:
                        if not text:
                            return ""
                        max_len = 800
                        if len(text) > max_len:
                            return f"{label} (first {max_len} characters):\n{text[:max_len]}\n... [cut off]\n"
                        return f"{label}:\n{text}\n"

                    snippet_blocks = []
                    if stdout:
                        snippet_blocks.append(_truncate(stdout, "STDOUT"))
                    if stderr:
                        snippet_blocks.append(_truncate(stderr, "STDERR"))

                    if snippet_blocks:
                        parts.append("\n" + "\n".join(snippet_blocks))

                elif tool_name == "edit_file" and success:
                    path = result.get("path") or args.get("path", "")
                    line_no = result.get("line") or args.get("line")
                    mode = result.get("mode") or ("line" if "line" in args else "old_string")
                    new_line = result.get("new_line")

                    summary = f" Result: edited (mode={mode}"
                    if line_no:
                        summary += f", line={line_no}"
                    if path:
                        summary += f", path={path}"
                    summary += ")."
                    parts.append(summary)

                    if new_line:
                        parts.append(f" New line: {new_line}")

                elif tool_name == "search_files" and success:
                    count = result.get("count", 0)
                    matches = result.get("matches") or []
                    parts.append(f" Result: {count} matches.")

                    # 展示前若干条匹配，避免一次性塞太多
                    max_items = 5
                    if matches:
                        parts.append(" First matches:")
                        for m in matches[:max_items]:
                            parts.append(f"  - {m.get('file')}:{m.get('line')}: {m.get('content')}")
                        if count > max_items:
                            parts.append(f"  ... and {count - max_items} more.")

                elif tool_name == "find_files" and success:
                    count = result.get("count", 0)
                    matches = result.get("matches") or []
                    parts.append(f" Result: {count} files.")

                    max_items = 10
                    if matches:
                        parts.append(" First files:")
                        for p in matches[:max_items]:
                            parts.append(f"  - {p}")
                        if count > max_items:
                            parts.append(f"  ... and {count - max_items} more.")

                else:
                    # 其他工具：直接给出一个截断后的 JSON 视图，避免完全丢信息
                    try:
                        result_json = json.dumps(result, ensure_ascii=False)
                        max_len = 800
                        if len(result_json) > max_len:
                            result_json = result_json[:max_len] + "... [cut off]"
                        parts.append(f" Result(raw): {result_json}")
                    except Exception:
                        parts.append(f" Result: {result}")

            # 原来的“重要提示”在很多情况下与事实不符，这里注释掉保留作为学习对比
            # parts.append("\n## 重要提示")
            # parts.append("你已经在历史记录中看到了代码内容，请分析它并决定下一步该做什么！")
            # parts.append("不要再次读取文件，除非你需要查看其他文件。")
            # parts.append("绝对不要修改已经修复好的代码！")
        
        return "\n".join(parts)


ENV_KEYS = {
    "ANTHROPIC_API_KEY": "api_key",
    "ANTHROPIC_BASE_URL": "base_url",
    "MODEL_ID": "model",
    "MAX_TOKENS": "max_tokens",
}


def config_paths() -> list:
    """按优先级从高到低返回 .env 候选路径"""
    paths = [Path.cwd() / ".env", USER_CONFIG]
    # 只有从源码目录运行时才读仓库里的 .env（pip 安装后 REPO_DIR 是 site-packages）
    if (REPO_DIR / "pyproject.toml").is_file():
        paths.append(REPO_DIR / ".env")
    return paths


def _read_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config():
    """加载配置

    优先级：环境变量 > 当前目录 .env > ~/.config/cookierookie/.env > 仓库根目录 .env
    """
    config = {
        "api_key": None,
        "model": "MiniMax-M2.5",
        "base_url": "https://api.minimax.io/anthropic",
        "max_tokens": DEFAULT_MAX_TOKENS,
    }

    # 先读优先级低的，后读的覆盖前面的
    for path in reversed(config_paths()):
        if path.is_file():
            for key, value in _read_env_file(path).items():
                if key in ENV_KEYS and value:
                    config[ENV_KEYS[key]] = value

    for key, field in ENV_KEYS.items():
        if os.environ.get(key):
            config[field] = os.environ[key]

    try:
        config["max_tokens"] = int(config["max_tokens"])
    except ValueError:
        print(f"Warning: MAX_TOKENS={config['max_tokens']!r} is not a number, using {DEFAULT_MAX_TOKENS}")
        config["max_tokens"] = DEFAULT_MAX_TOKENS

    return config


def print_missing_key_help():
    print("Error: ANTHROPIC_API_KEY not found.")
    print("Set it in one of these places:")
    print("  - environment variable: export ANTHROPIC_API_KEY=...")
    for path in config_paths():
        print(f"  - {path}")
    print("See .env.example in the repository for all options.")


def main(bug_report: str, yes: bool = False):
    """Debug 模式。yes=True 时修改文件和执行命令前不询问"""
    # 加载配置
    config = load_config()
    
    if not config["api_key"]:
        print_missing_key_help()
        return
    
    print(f"Config: model={config['model']}, base_url={config['base_url']}")
    
    # 创建客户端和 agent
    llm_client = LLMClient(
        config["api_key"], 
        config["model"], 
        config["base_url"],
        config["max_tokens"],
    )
    agent = DebugAgent(llm_client, ask=approve_all if yes else None)

    # 运行
    print(f"Starting Debug Agent ({config['model']})...")
    print(f"Bug: {bug_report}")
    if yes:
        print("--yes: edits and commands run without asking.")
    else:
        print("You'll be asked before each file edit or command.")
    print()

    try:
        result = agent.run(bug_report)
    except KeyboardInterrupt:
        print("\nInterrupted")
        return
    print(f"\n=== Final Result ===\n{result}")


def parse_edit_args(text: str) -> dict:
    """Parse what follows /edit: key=value pairs. Quote values that contain spaces."""
    changes = {}
    for part in shlex.split(text):
        key, sep, value = part.partition("=")
        if not sep or not key.isidentifier():
            raise ValueError(f"expected key=value, got {part!r}")
        changes[key] = value
    if not changes:
        raise ValueError("give at least one key=value")
    return changes


def interactive_main():
    """交互模式入口"""
    config = load_config()

    if not config["api_key"]:
        print_missing_key_help()
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print(f"Working in: {Path.cwd()}")
    print("Type 'exit' to quit, 'help' for commands\n")

    # 初始化组件
    from cookierookie.tool_system import tool_system
    from cookierookie import tools as tools_module
    tools_module.register_base_tools()

    from cookierookie.core import create_interactive_agent

    llm_client = LLMClient(
        config["api_key"],
        config["model"],
        config["base_url"],
        config["max_tokens"],
    )
    agent = create_interactive_agent(llm_client, tool_system)
    agent.current_plan = None

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
                if not agent.pending_action:
                    print("No pending action to edit")
                    continue
                try:
                    changes = parse_edit_args(user_input[len("/edit"):])
                except ValueError as e:
                    print(f'Invalid /edit: {e}. Example: /edit command="python -m pytest -q"')
                    continue
                result = agent.edit_and_confirm(changes)
                print(f"\n{result}\n")
                continue

            if user_input == "/status":
                if agent.pending_action:
                    agent._show_pending_action()
                else:
                    print("No pending action")
                continue

            if user_input == "/plan":
                if hasattr(agent, 'current_plan') and agent.current_plan:
                    formatted = agent._format_plan(agent.current_plan)
                    print(f"\n{formatted}\n")
                else:
                    print("No plan available. Enter a task first.")
                continue

            if user_input.startswith("/skip"):
                parts = user_input.split()
                if len(parts) > 1:
                    try:
                        step_num = int(parts[1])
                        if hasattr(agent, 'skip_step'):
                            result = agent.skip_step(step_num)
                            print(f"\n{result}\n")
                        else:
                            print("Skip not supported")
                    except ValueError:
                        print("Invalid step number")
                continue

            if user_input in ["/help", "/h", "help"]:
                print("""
CookieRookie Coding Agent

Type a task and the agent works on it. Reading and searching run on their own;
each file edit or command waits for one of these:

  /confirm                      Run it
  /reject [what to do instead]  Don't run it. With a reason, the agent tries another way;
                                without one, the task stops
  /edit key=value ...           Change some of its arguments, then run it,
                                e.g. /edit command="python -m pytest -q"
  /status                       Show what is waiting

  /plan                         Show the current plan
  /skip <step>                  Skip a step of the plan
  exit, quit                    Leave

Examples:
  > write a calculator module with add and divide
  > 为 src/calculator.py 生成测试
  > fix the login bug in auth.py
""")
                continue

            # 普通任务
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


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cookierookie",
        description="An AI coding agent that works on the project in the current directory. "
                    "Without a bug description it starts interactive mode.",
    )
    parser.add_argument("bug", nargs="?", help="debug mode: describe the bug to find and fix")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="debug mode: edit files and run commands without asking first")
    parser.add_argument("--interactive", action="store_true", help=argparse.SUPPRESS)  # same as no arguments
    args = parser.parse_args(argv)

    if not args.interactive and not args.bug:
        args.bug = os.environ.get("DEBUG_BUG_REPORT") or None
    if args.yes and (args.interactive or not args.bug):
        parser.error('--yes only applies to debug mode, e.g. cookierookie --yes "the bug"')
    return args


def run():
    """命令行入口（pyproject.toml 中的 cookierookie 命令）"""
    args = parse_args()
    if args.interactive or not args.bug:
        interactive_main()
    else:
        main(args.bug, args.yes)


if __name__ == "__main__":
    run()
