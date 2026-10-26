"""
Debug Agent entry point
Works with several LLM providers (Minimax, DeepSeek, Kimi, GLM, Anthropic)
"""

import ast
import os
import sys
import json
import re
import shlex
import requests

from agent.history import compact_history

# Add this file's folder to the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import DebugAgent
from agent.core import create_interactive_agent, approve_all


# The folder this file is in
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# Longest reply the model may write. write_file sends a whole file in one reply, so this must not
# be small. Set MAX_TOKENS in .env to change it.
DEFAULT_MAX_TOKENS = 8192

# (connect, read) timeouts in seconds. The API sends nothing until the whole reply is written, and
# writing up to DEFAULT_MAX_TOKENS can take minutes, so a 60-second read timeout cut long replies off.
REQUEST_TIMEOUT = (10, 300)

# Most of a source file test_generate shows the model. Tests are written for the whole file, so
# this is larger than the 2000 characters a read_file step shows.
MAX_SOURCE_CHARS = 12000


class LLMClient:
    """LLM client for any API that speaks the Anthropic Messages format"""
    
    def __init__(self, api_key: str, model: str = "MiniMax-M3", base_url: str = "https://api.minimax.io/anthropic",
                 max_tokens: int = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens or load_config()["max_tokens"]
        # Offer the tools through the API's tool use. Turned off for the rest of the session if
        # the API refuses a request that has them (a gateway without tool use)
        self.use_tools = True

    def chat(self, context: dict) -> dict:
        """Call the LLM API (Anthropic Messages format)"""
        # Older steps lose their file contents and output, so long tasks still fit the context window
        messages = [
            {"role": "user", "content": self._build_user_message(compact_history(context))}
        ]
        
        # Add the system prompt
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
        # The agents put the tools they can run in the context (planning offers none). The model
        # can then call one as a tool_use block, whose arguments arrive as JSON: no quoting or
        # escaping to get wrong, which broke write_file and multi-line edits in the text format
        tools = context.get("tools") if self.use_tools else None
        if tools:
            data["tools"] = tools

        # "fatal" stops the run and shows the error instead of calling the API again and again.
        # Every API error and network failure is fatal for now, including ones a later retry
        # could fix (429 rate limits, 5xx); so is a reply cut off at max_tokens.
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            if tools and response.status_code in (400, 422):
                # Some Anthropic-compatible gateways don't take "tools": ask again without them.
                # The text format (thought:/action:/done:) still works there
                data.pop("tools")
                retry = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=data,
                    timeout=REQUEST_TIMEOUT
                )
                # Only a request that works without tools shows that they were the problem. A wrong
                # MODEL_ID is a 400 either way; it used to turn tool use off for the whole session
                if retry.status_code == 200:
                    print("Note: the API refused the request with tools, so CookieRookie uses the text reply format.")
                    self.use_tools = False
                    response = retry
        except requests.RequestException as e:
            return {"action": None, "fatal": True, "raw": "",
                    "error": f"Could not reach {self.base_url}: {type(e).__name__}: {e}"}

        if response.status_code != 200:
            return {"action": None, "fatal": True, "raw": response.text,
                    "error": f"API error: {response.status_code} - {response.text[:500]}"}
        
        # A wrong ANTHROPIC_BASE_URL can answer 200 with a web page, and some Anthropic-compatible
        # gateways report errors (no balance, unknown model) with status 200. Before, a page crashed
        # debug mode with a traceback, and an error body was read as an empty reply and sent again
        try:
            result = response.json()
        except ValueError:
            return {"action": None, "fatal": True, "raw": response.text,
                    "error": (f"The API at {self.base_url} did not answer with JSON: {response.text[:200]!r}. "
                              "Check ANTHROPIC_BASE_URL (it is the part before /v1/messages).")}
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            return {"action": None, "fatal": True, "raw": response.text,
                    "error": f"API error: the reply has no content - {response.text[:500]}"}

        # Go through all content blocks
        texts = []
        tool_calls = []
        thinking_content = ""

        for block in result["content"]:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                tool_calls.append(block)
            elif block.get("type") == "thinking":
                thinking_content = block.get("thinking", "")
        json_content = "\n".join(t for t in texts if t.strip())
        
        # Print the thinking (for debugging)
        if thinking_content:
            print(f"\n=== LLM Thinking ===\n{thinking_content[:300]}...\n=====================\n")
        
        # A reply cut off at max_tokens would be read as a half-written action (a file without its
        # end, a command without its last argument), so it is reported instead of run
        if result.get("stop_reason") == "max_tokens":
            return {"action": None, "fatal": True, "raw": json_content,
                    "error": (f"The reply was cut off at max_tokens={self.max_tokens}. "
                              "Set a larger MAX_TOKENS in .env, or ask for a smaller step.")}

        if tool_calls:
            return self._tool_call_reply(json_content, tool_calls[0])

        # Read the reply in the text format
        parsed = self._parse_response(json_content)
        
        if parsed:
            parsed["raw"] = json_content
            return parsed

        # With tool use, a model that has finished often just answers in prose, without
        # "done: true". That is its final answer, not a reply in the wrong format
        if tools and self.use_tools and json_content.strip() and result.get("stop_reason") == "end_turn":
            return {"thought": "", "action": {}, "done": True, "summary": json_content.strip(),
                    "raw": json_content}

        return {"action": None, "error": f"Failed to parse: {json_content[:200]}", "raw": json_content}
    
    def _tool_call_reply(self, text: str, call: dict) -> dict:
        """A reply that called a tool through tool use. The text next to the call is the thought.
        One tool runs per step, so a second call in the same reply is left for the next step."""
        args = call.get("input")
        args = args if isinstance(args, dict) else {}
        fields = self._reply_fields(text)
        thought = fields.get("thought", text).strip("*").strip()
        shown = json.dumps(args, ensure_ascii=False)
        return {
            "thought": thought,
            "action": {"tool": call.get("name", ""), "args": args},
            "done": False,
            "summary": "",
            "raw": (text + "\n" if text else "") + f"[tool call] {call.get('name', '')}({shown})",
        }

    # A "thought:", "action:", "done:" or "summary:" line, also the ways models dress it up:
    # "Thought:", "**action:**", "**Done**:", "- summary:"
    REPLY_LABEL = re.compile(r'^[\s>*_#-]*(thought|action|done|summary)[*_`\s]*:[*_\s]*(.*)$', re.IGNORECASE)

    @classmethod
    def _reply_fields(cls, content: str) -> dict:
        """The text after each label line, up to the next label line. Before, the labels had to be
        lower case and at the very start of a line, so "Thought:" or "**action:**" gave no action,
        and "action:" inside the thought was taken as the action. Inside the action only "done:"
        ends it, so a file written with write_file may contain lines like "summary: ..."."""
        fields, current = {}, None
        for line in content.splitlines():
            match = cls.REPLY_LABEL.match(line)
            label = match.group(1).lower() if match else None
            if label and label not in fields and (current != "action" or label == "done"):
                current = label
                fields[current] = [match.group(2)]
            elif current:
                fields[current].append(line)
        values = {}
        for label, lines in fields.items():
            # A reply wrapped in a ``` block leaves the closing fence on the last field
            while lines and lines[-1].strip().startswith("```"):
                lines.pop()
            values[label] = "\n".join(lines).strip()
        return values

    def _parse_response(self, content: str) -> dict:
        """Parse the LLM reply - accepts several formats"""
        fields = self._reply_fields(content.strip())

        result = {
            "thought": fields.get("thought", "").strip("*").strip(),
            "action": {},
            "done": False,
            "summary": fields.get("summary", "")
        }

        # action: `read_file(path="a.py")` - the backticks are not part of the call
        action_str = fields.get("action", "").strip("`").strip()
        if action_str:
            parsed = self._parse_action(action_str)
            if parsed:
                tool_name, args = parsed
                result["action"] = {"tool": tool_name, "args": args}

        done_match = re.match(r'\W*(true|false)', fields.get("done", ""), re.IGNORECASE)
        if done_match:
            result["done"] = done_match.group(1).lower() == "true"

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
        """Read tool arguments from text Python can't parse (numbers, "double" and 'single' quoted strings)"""
        args = {}
        
        # Number arguments: key=123
        for match in re.finditer(r'(\w+)=(\d+)', args_str):
            args[match.group(1)] = int(match.group(2))
        
        # Double-quoted strings: key="value"
        for match in re.finditer(r'(\w+)="((?:[^"\\]|\\.)*)"', args_str):
            key = match.group(1)
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            args[key] = value
        
        # Single-quoted strings: key='value'
        for match in re.finditer(r'(\w+)=\'((?:[^\'\\]|\\.)*)\'', args_str):
            key = match.group(1)
            value = match.group(2).replace("\\'", "'").replace('\\\\', '\\')
            args[key] = value
        
        return args
    
    def _build_user_message(self, context: dict) -> str:
        """Build the user message"""
        parts = []
        
        # Debug mode sends bug_report, interactive mode sends task
        if context.get("bug_report"):
            parts.append(f"## Bug Report\n{context['bug_report']}")
        else:
            parts.append(f"## Task\n{context.get('task', '')}")

        # Project memory (added by InteractiveAgent in interactive mode)
        if context.get("memory"):
            parts.append("\n" + context["memory"])
        
        # History
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
                            # Quoted and escaped, so the line is a call the reply format accepts.
                            # Before, f'{k}="{v}"' wrote new_string="print("hi")" and real line
                            # breaks, and models copied that broken quoting into their next action
                            args_parts.append(f'{k}={json.dumps(v, ensure_ascii=False)}' if isinstance(v, str) else f'{k}={v}')
                    args_str = ", ".join(args_parts)
                    parts.append(f" Action: {tool_name}({args_str})")
                
                # ===== Old result summary (kept for comparison while learning) =====
                # if tool_name == "read_file" and result.get("success"):
                #     parts.append(f" Result: file content read")
                # elif tool_name == "exec" and result.get("success"):
                #     stdout = result.get("stdout", "").strip()
                #     if len(stdout) > 100:
                #         stdout = stdout[:100] + "..."
                #     parts.append(f" Result: {stdout}")
                # elif tool_name == "edit_file" and result.get("success"):
                #     parts.append(f" Result: file edited")
                # elif not result.get("success"):
                #     parts.append(f" Result: failed - {result.get('error', result.get('stderr', 'unknown'))}")
                # else:
                #     parts.append(f" Result: success")

                # ===== New result summary: keep the status and the key details =====
                success = result.get("success")

                # Failures in one place. A command or test run that ran and exited with an error is
                # shown by its own branch below: here it showed only stderr, so a failing
                # `exec(command="pytest")`, which prints to stdout, reached the model as "failed - "
                ran = tool_name in ("exec", "test_run") and "returncode" in result
                if success is False and not ran:
                    error_msg = result.get("error", result.get("stderr", "unknown"))
                    parts.append(f" Result: failed - {error_msg}")
                    continue

                # No result
                if result is None:
                    parts.append(" Result: (no result)")
                    continue

                # Per tool: a one-line summary plus the key fields
                if tool_name == "read_file" and success:
                    lines = result.get("lines", "?")
                    total = result.get("total", "?")
                    content = result.get("content", "")

                    parts.append(f" Result: read lines {lines} (of {total}).")

                    # Cut long files, but say so
                    max_chars = 2000
                    # With line numbers: the model is told to edit by line number (edit_file line=N),
                    # and without them it had to count lines and often edited the one next to the bug
                    first = str(lines).split("-")[0]
                    first = int(first) if first.isdigit() else 1
                    snippet = "".join(f"{n:>4} | {text}" for n, text in enumerate(content.splitlines(keepends=True), first))
                    if snippet:
                        snippet = "(line number | text; the numbers are not part of the file)\n" + snippet
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

                    # Show the first few matches instead of all of them
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

                elif tool_name == "test_generate" and success:
                    # Before, this went through the 800-character JSON view below: the model saw
                    # the start of the source and never the test file path or the hint after it
                    source = result.get("source") or args.get("source", "")
                    parts.append(f" Result: read {source} to write tests for it. Write them to "
                                 f"{result.get('target')} ({result.get('framework')}).")
                    content = result.get("source_content")
                    if content:
                        snippet = "".join(f"{n:>4} | {text}" for n, text in
                                          enumerate(content.splitlines(keepends=True), 1))
                        if len(snippet) > MAX_SOURCE_CHARS:
                            snippet = (snippet[:MAX_SOURCE_CHARS] + f"\n... [cut off: read the rest of "
                                       f"{source} with read_file before writing tests for it]")
                        parts.append("\n```code\n(line number | text; the numbers are not part of the file)\n"
                                     + snippet + "\n```")
                    if result.get("framework_hint"):
                        parts.append(result["framework_hint"].rstrip())

                else:
                    # Other tools: a shortened JSON view, so nothing is lost entirely
                    try:
                        result_json = json.dumps(result, ensure_ascii=False)
                        max_len = 800
                        if len(result_json) > max_len:
                            result_json = result_json[:max_len] + "... [cut off]"
                        parts.append(f" Result(raw): {result_json}")
                    except Exception:
                        parts.append(f" Result: {result}")

            # The old "important notes" were often wrong, so they are commented out and kept for comparison
            # parts.append("\n## Important notes")
            # parts.append("You have already seen the code in the history. Analyze it and decide what to do next!")
            # parts.append("Do not read the file again unless you need to look at another file.")
            # parts.append("Never change code that is already fixed!")
        
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
        "model": "MiniMax-M3",
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
        print(f"Usage: {PROG} [--yes] \"Your bug description\"")
        print("Or set DEBUG_BUG_REPORT environment variable")
        print("--yes, -y: run edits and commands without asking")
        return
    
    # Load the settings
    config = load_config()
    
    if not config["api_key"]:
        print_missing_key()
        return
    
    print(f"Config: model={config['model']}, base_url={config['base_url']}")
    
    # Create the client and the agent
    llm_client = LLMClient(
        config["api_key"], 
        config["model"], 
        config["base_url"]
    )
    agent = DebugAgent(llm_client, ask=approve_all if approve else None)
    
    # Run
    print(f"Starting Debug Agent ({config['model']})...")
    print(f"Bug: {bug_report}\n")
    
    result = agent.run(bug_report)
    print(f"\n=== Final Result ===\n{result}")


def interactive_main():
    """Interactive mode entry point"""
    config = load_config()

    if not config["api_key"]:
        print_missing_key()
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print("Type 'exit' to quit, 'help' for commands\n")

    # Set up the components
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

            # A normal task
            result = agent.run(user_input)

            if result == "awaiting_confirmation":
                # Wait for the user to confirm in the next round
                pass
            else:
                print(f"\n{result}\n")

        except KeyboardInterrupt:
            print("\nStopped the current task. Type exit (or press Ctrl+C again) to quit.")
        except Exception as e:
            print(f"Error: {e}")


# How the user started CookieRookie: the installed `cookierookie` command (agent/cli.py sets this)
# or `python main.py` from a checkout. The help shows the command they can actually run.
PROG = os.environ.get("COOKIEROOKIE_PROG") or "python main.py"

USAGE = f"""Usage:
  {PROG} --interactive        Work on tasks interactively (type help inside for commands)
  {PROG} "bug description"    Debug mode: find and fix the bug
  {PROG} --help               Show this help"""

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
