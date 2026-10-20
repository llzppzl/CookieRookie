"""
Debug Agent 入口
支持多种 LLM 提供商 (Minimax, DeepSeek, Kimi, GLM, Anthropic)
"""

import ast
import os
import sys
import json
import re
import shlex
import requests

from agent.history import compact_history

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import DebugAgent
from agent.core import create_interactive_agent, approve_all


# 获取当前项目目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# Longest reply the model may write. write_file sends a whole file in one reply, so this must not
# be small. Set MAX_TOKENS in .env to change it.
DEFAULT_MAX_TOKENS = 8192

# (connect, read) timeouts in seconds. The API sends nothing until the whole reply is written, and
# writing up to DEFAULT_MAX_TOKENS can take minutes, so a 60-second read timeout cut long replies off.
REQUEST_TIMEOUT = (10, 300)


class LLMClient:
    """通用 LLM 客户端 (Anthropic 兼容模式)"""
    
    def __init__(self, api_key: str, model: str = "MiniMax-M2.5", base_url: str = "https://api.minimax.io/anthropic",
                 max_tokens: int = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens or load_config()["max_tokens"]
    
    def chat(self, context: dict) -> dict:
        """调用 LLM API (Anthropic 兼容格式)"""
        # Older steps lose their file contents and output, so long tasks still fit the context window
        messages = [
            {"role": "user", "content": self._build_user_message(compact_history(context))}
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
        
        # "fatal" marks errors that retrying won't fix (wrong key, no quota, cut-off reply):
        # the agent stops and shows them instead of calling the API again and again
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=data,
                timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as e:
            return {"action": None, "fatal": True, "raw": "",
                    "error": f"Could not reach {self.base_url}: {type(e).__name__}: {e}"}
        
        if response.status_code != 200:
            return {"action": None, "fatal": True, "raw": response.text,
                    "error": f"API error: {response.status_code} - {response.text[:500]}"}
        
        result = response.json()
        
        # 遍历所有 content blocks
        json_content = ""
        thinking_content = ""
        
        if "content" in result:
            for block in result["content"]:
                if block.get("type") == "text":
                    json_content = block.get("text", "")
                elif block.get("type") == "thinking":
                    thinking_content = block.get("thinking", "")
        
        # 打印 thinking（调试用）
        if thinking_content:
            print(f"\n=== LLM Thinking ===\n{thinking_content[:300]}...\n=====================\n")
        
        # A reply cut off at max_tokens would be read as a half-written action (a file without its
        # end, a command without its last argument), so it is reported instead of run
        if result.get("stop_reason") == "max_tokens":
            return {"action": None, "fatal": True, "raw": json_content,
                    "error": (f"The reply was cut off at max_tokens={self.max_tokens}. "
                              "Set a larger MAX_TOKENS in .env, or ask for a smaller step.")}
        
        # 解析响应
        parsed = self._parse_response(json_content)
        
        if parsed:
            parsed["raw"] = json_content
            return parsed
        
        return {"action": None, "error": f"Failed to parse: {json_content[:200]}", "raw": json_content}
    
    def _parse_response(self, content: str) -> dict:
        """解析 LLM 响应 - 支持多种格式"""
        content = content.strip()
        
        result = {
            "thought": "",
            "action": {},
            "done": False,
            "summary": ""
        }
        
        # 提取 thought
        thought_match = re.search(r'thought:\s*(.+?)(?=\naction:|$)', content, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()
        
        # 提取 action
        action_match = re.search(r'action:\s*(.+?)(?=\ndone:|$)', content, re.DOTALL)
        if action_match:
            action_str = action_match.group(1).strip()
            if action_str:
                parsed = self._parse_action(action_str)
                if parsed:
                    tool_name, args = parsed
                    result["action"] = {"tool": tool_name, "args": args}
        
        # 提取 done
        done_match = re.search(r'done:\s*(true|false)', content, re.IGNORECASE)
        if done_match:
            result["done"] = done_match.group(1).lower() == "true"
        
        # 提取 summary
        summary_match = re.search(r'summary:\s*(.+?)$', content, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()
        
        if not result["thought"] and not result["action"]:
            return None
        
        return result
    
    def _parse_action(self, action_str: str):
        """Parse `tool(key="value", n=1)` into (tool_name, args), or None if it isn't a call.

        The call is read like Python, so quotes, escapes (\\n becomes a line break), True/False
        and key=value text inside a string all work. A string with real line breaks in it is
        retried with them escaped. Anything Python can't read falls back to _parse_args.
        """
        for candidate in (action_str, action_str.replace("\n", "\\n")):
            try:
                call = ast.parse(candidate.strip(), mode="eval").body
            except SyntaxError:
                continue
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)) or call.args:
                continue
            try:
                args = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}
            except ValueError:
                continue
            return call.func.id, args

        func_match = re.match(r'(\w+)\((.*)\)', action_str, re.DOTALL)
        if func_match:
            return func_match.group(1), self._parse_args(func_match.group(2))
        return None

    def _parse_args(self, args_str: str) -> dict:
        """解析工具参数 - 支持多种格式"""
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
        
        # Debug mode sends bug_report, interactive mode sends task
        if context.get("bug_report"):
            parts.append(f"## Bug Report\n{context['bug_report']}")
        else:
            parts.append(f"## Task\n{context.get('task', '')}")

        # Project memory (added by InteractiveAgent in interactive mode)
        if context.get("memory"):
            parts.append("\n" + context["memory"])
        
        # 历史记录
        if context["history"]:
            parts.append("\n## History (what you have done so far)")
            for h in context["history"]:
                action = h.get("action", {})
                result = h.get("result", {})
                thought = h.get("thought", "")
                iteration = h.get("iteration", "?")
                
                tool_name = action.get("tool", "unknown")
                args = action.get("args", {})
                
                parts.append(f"\n### Step {iteration}")
                parts.append(f" Thought: {thought}")
                
                if tool_name and tool_name != "unknown":
                    args_parts = []
                    for k, v in args.items():
                        if k == "new_string" and len(str(v)) > 50:
                            args_parts.append(f'{k}="[cut off]"')
                        else:
                            args_parts.append(f'{k}="{v}"' if isinstance(v, str) else f'{k}={v}')
                    args_str = ", ".join(args_parts)
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
                success = result.get("success")

                # Failures in one place (a test run that ran but had failures is shown by the test_run branch below)
                if success is False and not (tool_name == "test_run" and "returncode" in result):
                    error_msg = result.get("error", result.get("stderr", "unknown"))
                    parts.append(f" Result: failed - {error_msg}")
                    continue

                # 没有 result 的情况
                if result is None:
                    parts.append(" Result: (no result)")
                    continue

                # 按工具类型分别给出「一句话总结 + 关键字段」
                if tool_name == "read_file" and success:
                    lines = result.get("lines", "?")
                    total = result.get("total", "?")
                    content = result.get("content", "")

                    parts.append(f" Result: read lines {lines} (of {total}).")

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

                    parts.append(f" Result: the command finished with returncode={returncode}.")

                    def _truncate(text: str, label: str) -> str:
                        if not text:
                            return ""
                        max_len = 800
                        if len(text) > max_len:
                            return f"{label} (the first {max_len} characters):\n{text[:max_len]}\n... [cut off]\n"
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
                            parts.append(f"  ... {count - max_items} more not shown.")

                elif tool_name == "find_files" and success:
                    count = result.get("count", 0)
                    matches = result.get("matches") or []
                    parts.append(f" Result: {count} files found.")

                    max_items = 10
                    if matches:
                        parts.append(" First files:")
                        for p in matches[:max_items]:
                            parts.append(f"  - {p}")
                        if count > max_items:
                            parts.append(f"  ... {count - max_items} more not shown.")

                elif tool_name == "test_run":
                    # The failures and the counts come last, so keep the end of the output (the JSON view below would cut them off)
                    counts = ", ".join(f"{key}: {result[key]}" for key in ("passed", "failed", "errors")
                                       if result.get(key))
                    parts.append(f" Result: {result.get('command') or 'the tests'} exited with code "
                                 f"{result.get('returncode')}" + (f" ({counts})" if counts else "") + ".")
                    output = ((result.get("stdout") or "") + (result.get("stderr") or "")).strip()
                    max_len = 2000
                    if len(output) > max_len:
                        parts.append(f"\nOutput (the last {max_len} characters):\n[cut off] ...{output[-max_len:]}")
                    elif output:
                        parts.append(f"\nOutput:\n{output}")

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


# Environment variable -> config key. Each one can also be set in .env.
ENV_SETTINGS = {
    "ANTHROPIC_API_KEY": "api_key",
    "ANTHROPIC_BASE_URL": "base_url",
    "MODEL_ID": "model",
}
API_KEY_PLACEHOLDER = "your-api-key-here"


def print_missing_key():
    print("Error: no API key found.")
    print(f"Set ANTHROPIC_API_KEY in {os.path.join(PROJECT_DIR, '.env')} (copy .env.example to start)")
    print("or in your environment: export ANTHROPIC_API_KEY=your-key")


def load_config():
    """Load settings from .env in the CookieRookie folder, then from environment variables (which win)"""
    env_path = os.path.join(PROJECT_DIR, ".env")
    
    config = {
        "api_key": None,
        "model": "MiniMax-M2.5",
        "base_url": "https://api.minimax.io/anthropic",
        "max_tokens": DEFAULT_MAX_TOKENS,
    }
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    config["api_key"] = line.split("=", 1)[1].strip()
                elif line.startswith("ANTHROPIC_BASE_URL="):
                    config["base_url"] = line.split("=", 1)[1].strip()
                elif line.startswith("MODEL_ID="):
                    config["model"] = line.split("=", 1)[1].strip()
                elif line.startswith("MAX_TOKENS="):
                    value = line.split("=", 1)[1].strip()
                    if value.isdigit() and int(value) > 0:
                        config["max_tokens"] = int(value)
    
    # Environment variables win over .env, so `export ANTHROPIC_API_KEY=...` works without a .env file
    for env_name, key in ENV_SETTINGS.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            config[key] = value

    # KEY="value" and KEY='value' are common in .env files: the quotes are not part of the value
    for key, value in config.items():
        if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            config[key] = value[1:-1].strip()

    # An empty key or the placeholder from .env.example counts as no key
    if config["api_key"] in ("", API_KEY_PLACEHOLDER):
        config["api_key"] = None

    return config


def main():
    # Bug description; --yes / -y runs edits and commands without asking
    args = sys.argv[1:]
    approve = any(a in ("--yes", "-y") for a in args)
    args = [a for a in args if a not in ("--yes", "-y")]
    bug_report = args[0] if args else os.environ.get("DEBUG_BUG_REPORT", "")
    
    if not bug_report:
        print("Usage: python main.py [--yes] \"Your bug description\"")
        print("Or set DEBUG_BUG_REPORT environment variable")
        print("--yes, -y: run edits and commands without asking")
        return
    
    # 加载配置
    config = load_config()
    
    if not config["api_key"]:
        print_missing_key()
        return
    
    print(f"Config: model={config['model']}, base_url={config['base_url']}")
    
    # 创建客户端和 agent
    llm_client = LLMClient(
        config["api_key"], 
        config["model"], 
        config["base_url"]
    )
    agent = DebugAgent(llm_client, ask=approve_all if approve else None)
    
    # 运行
    print(f"Starting Debug Agent ({config['model']})...")
    print(f"Bug: {bug_report}\n")
    
    result = agent.run(bug_report)
    print(f"\n=== Final Result ===\n{result}")


def interactive_main():
    """交互模式入口"""
    config = load_config()

    if not config["api_key"]:
        print_missing_key()
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print("Type 'exit' to quit, 'help' for commands\n")

    # 初始化组件
    from agent.tool_system import tool_system
    from agent import tools as tools_module
    tools_module.register_base_tools()
    # git tools run git in the current directory: the project CookieRookie was started in
    from agent.git_tools import register_git_tools
    register_git_tools()

    from agent.core import create_interactive_agent

    llm_client = LLMClient(
        config["api_key"],
        config["model"],
        config["base_url"]
    )
    # The folder you start CookieRookie in is the project it works on: it remembers that folder's
    # layout in .agent-memory.json there and tells the model about it
    agent = create_interactive_agent(llm_client, tool_system, project_path=os.getcwd())
    agent.current_plan = None

    while True:
        # Ctrl+C at the prompt quits; Ctrl+C while a task runs only stops that task
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            # EOFError: Ctrl+D, or stdin closed. It used to fall through to "except Exception",
            # print "Error: " and ask again, forever
            print()
            break

        try:
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                break

            if user_input == "/confirm":
                # An edit or command that is waiting is answered before the plan
                if agent.pending_action:
                    result = agent.confirm()
                elif agent.current_plan:
                    result = agent.execute_plan()
                else:
                    result = "Nothing to confirm"
                if result != "awaiting_confirmation":
                    print(f"\n{result}\n")
                continue

            if user_input.startswith("/reject"):
                parts = user_input.split(" ", 1)
                instructions = parts[1].strip() if len(parts) > 1 else None
                if not agent.pending_action and agent.current_plan:
                    # With instructions the model changes the plan; without, the plan is dropped
                    if instructions:
                        result = agent.propose_plan(agent.current_plan["task"], instructions)
                    else:
                        result = agent.drop_plan()
                else:
                    result = agent.reject(instructions)
                print(f"\n{result}\n")
                continue

            if user_input.startswith("/edit"):
                # shlex keeps a quoted value with spaces together: /edit command="pytest -x"
                try:
                    words = shlex.split(user_input[5:].strip())
                except ValueError as e:
                    print(f"Invalid /edit usage: {e}")
                    continue
                modifications = {}
                for part in words:
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

            if user_input == "/plan" or user_input.startswith("/plan "):
                # /plan <task> asks for a plan (nothing runs); /plan alone shows the current one
                task = user_input[len("/plan"):].strip()
                result = agent.propose_plan(task) if task else agent.show_plan()
                print(f"\n{result}\n")
                continue

            if user_input == "/skip" or user_input.startswith("/skip "):
                parts = user_input.split()
                try:
                    step_num = int(parts[1])
                except (IndexError, ValueError):
                    print("Usage: /skip N (the step number shown in the plan)")
                    continue
                print(f"\n{agent.skip_step(step_num)}\n")
                continue

            if user_input in ["/help", "/h", "help"]:
                print("""
CookieRookie Coding Agent - commands

Tasks:
  Type a task and the agent works on it. Edits and commands wait for /confirm.

While an edit or command is waiting:
  /confirm          Run it
  /reject [why]     Don't run it (with a reason, the agent tries something else)
  /edit key=value   Change its arguments, then run it
  /status           Show what is waiting

Plans:
  /plan <task>      Ask for a step-by-step plan first; nothing runs yet
  /plan             Show the current plan
  /skip N           Leave out step N
  /confirm          Run the plan (edits and commands in it still wait for /confirm)
  /reject [change]  Change the plan as you say, or drop it

Quit:
  exit, quit

Examples:
  > Write a calculator module
  > /plan Add tests for src/calculator.py
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
            print("\nStopped the current task. Type exit (or press Ctrl+C again) to quit.")
        except Exception as e:
            print(f"Error: {e}")


USAGE = """Usage:
  python main.py --interactive        Work on tasks interactively (type help inside for commands)
  python main.py "bug description"    Debug mode: find and fix the bug
  python main.py --help               Show this help"""

# Options main() reads itself (--yes and -y skip the questions before edits in debug mode)
DEBUG_MODE_OPTIONS = ("--yes", "-y")


def cli(argv) -> int:
    """Pick the mode from the command line. Returns the exit code."""
    first = argv[0] if argv else ""
    if first in ("-h", "--help"):
        print(USAGE)
        return 0
    if first == "--interactive":
        interactive_main()
        return 0
    # An option-like word (no spaces) that isn't an option: a typo such as --interactiv used to be
    # taken as the bug report and sent to the model
    if first.startswith("-") and " " not in first and first not in DEBUG_MODE_OPTIONS:
        print(f"Unknown option: {first}\n\n{USAGE}")
        return 2
    main()
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
