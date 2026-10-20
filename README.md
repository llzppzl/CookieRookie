# CookieRookie

An autonomous AI coding agent that understands your codebase, writes code, generates tests, and helps you build features — with you in control.

## Features

- 🤖 **LLM-Powered** - Uses any Anthropic-compatible API (Minimax, DeepSeek, Kimi, etc.)
- 🛠️ **Tool Execution** - Read, edit, write files; execute commands; run tests
- 🔧 **Auto-Debug** - Automatically reads, analyzes, and fixes bugs
- 📋 **Task Planning** - Multi-step plans with full visibility and control
- 💾 **Project Memory** - Learns your project structure automatically
- 🔄 **Interactive Confirmation** - You confirm dangerous actions before execution

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API key

# 3. Run in interactive mode
python main.py --interactive
```

### Install as a command (optional)

To use CookieRookie in any project folder without typing the path to `main.py`, install it from your clone:

```bash
pip install -e .
cd /path/to/your/project
cookierookie --interactive
```

`cookierookie` takes the same arguments as `python main.py`. It works on the files of the folder you run it in, and reads `.env` from the clone. Run `pip install -e ".[test]"` to get pytest as well.

## Two Modes

### Interactive Mode (Recommended)

```bash
python main.py --interactive
> help  # Show available commands
> Write a calculator module
> Generate tests for src/calculator.py
> Fix the bug in the login function
```

### Debug Mode (Original)

```bash
python main.py "Your bug description here"
```

Before each file edit or shell command, the agent shows what it will do and asks:
`y` runs it, Enter or `n` skips it, `a` allows the rest of the run, `q` stops.
Anything else you type skips the step and is passed to the agent as feedback.
Pass `--yes` to run everything without asking.

## Configuration

Create a `.env` file:

```bash
ANTHROPIC_API_KEY=your-api-key-here
MODEL_ID=MiniMax-M2.5
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
# Optional: longest reply in tokens (default 8192). Raise it if replies get cut off.
MAX_TOKENS=8192
```

If the API returns an error (wrong key, no quota) or a reply is cut off at `MAX_TOKENS`, the agent stops and shows the error instead of retrying.

### Supported Models

| Provider | Model ID | Base URL |
|----------|----------|----------|
| Minimax | `MiniMax-M2.5` | `https://api.minimax.io/anthropic` |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/anthropic` |
| Kimi | `kimi-k2.5` | `https://api.moonshot.ai/anthropic` |
| GLM | `glm-5` | `https://api.z.ai/api/anthropic` |
| Anthropic | `claude-sonnet-4-6` | `https://api.anthropic.com` |

## Interactive Commands

| Command | Description |
|---------|-------------|
| `help` | Show help information |
| `/confirm` | Confirm and execute pending action |
| `/reject` | Reject and ask agent to replan |
| `/edit key=value` | Change some arguments of the pending action, then run it (e.g. `/edit line=19`, `/edit command="pytest -x"`) |
| `/status` | Show pending action status |
| `/plan <task>` | Ask for a step-by-step plan first; nothing runs yet |
| `/plan` | Show the current plan |
| `/skip N` | Leave out step N of the plan |
| `exit`, `quit` | Exit interactive mode |

## How It Works

### Planning Flow

```
1. You input a task
2. Agent plans multi-step execution
3. Agent shows you the plan
4. You confirm or modify
5. Agent executes step by step
   - Safe steps run automatically
   - Dangerous steps (edit, exec) pause for confirmation
```

### Available Tools

| Category | Tools |
|----------|-------|
| File | read_file, edit_file, write_file, search_files, find_files |
| Execute | exec |
| Git | git_status, git_diff, git_commit, git_branch, git_log, git_checkout |
| Test | test_run, test_generate |

The git tools work on the project in the directory you start CookieRookie in. `git_commit` and `git_checkout` wait for your `/confirm`.

## Project Structure

```
CookieRookie/
├── agent/
│   ├── __init__.py
│   ├── core.py              # Agent logic (DebugAgent, InteractiveAgent)
│   ├── tools.py             # Base file tools
│   ├── tool_system.py       # Plugin-based tool registry
│   ├── memory.py            # Project memory
│   ├── explorer.py          # Auto-detect project structure
│   ├── git_tools.py         # Git operations
│   ├── test_tools.py        # Test execution & generation (a tool module, not a test)
│   └── test_*.py            # Tests (run with: python -m pytest agent)
├── docs/superpowers/
│   ├── specs/               # Design specifications
│   └── plans/               # Implementation plans
├── test/                    # Small buggy files to try debug mode on
├── main.py                  # Entry point and LLM client
├── requirements.txt
└── .env.example
```

## Usage Examples

### Write Code

```bash
python main.py --interactive
> Write a user management module
# Agent plans and asks for confirmation
> /confirm
```

### Generate Tests

```bash
python main.py --interactive
> Generate tests for src/calculator.py
# Agent creates test file and runs it
```

### Debug

```bash
python main.py "calculator.py returns wrong result when dividing by zero"
```

### Plan Mode

```bash
python main.py --interactive
> /plan Refactor the login module and add tests

Plan: Refactor login() and cover it with tests

1. [read_file] Read src/auth.py
2. [write_file] Create tests/test_auth.py  (asks you first)
3. [edit_file] Refactor login()  (asks you first)
4. [test_run] Run the tests

/confirm to run it | /skip N to leave out step N | /reject [what to change]

> /skip 2
> /confirm
```

`/confirm` runs the plan as one task. Steps that edit files or run commands still wait for your `/confirm`. `/reject <what to change>` asks for a new plan; `/reject` alone drops it.

## Extending

### Adding New Tools

1. Implement the tool function in `agent/tools.py`:

```python
def my_tool(param1: str) -> dict:
    """Description of what the tool does"""
    return {"success": True, "result": "..."}
```

2. Register it in `register_base_tools()`:

```python
tool_system.register(
    "my_tool",
    my_tool,
    confirmable=True,  # Set True for dangerous operations
    description="Description for LLM"
)
```

### Changing System Prompt

Edit `SYSTEM_PROMPT` in `agent/core.py` to customize agent behavior.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         User (CLI)                          │
│     /confirm | /reject | /edit | /plan | /skip | exit        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     InteractiveAgent                         │
│   - Task planning (multi-step)                            │
│   - Confirmation mechanism                                 │
│   - Project memory (auto-inject context)                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                       ToolSystem                           │
│   - Plugin-based tool registry                           │
│   - confirmable flag management                          │
└──────────────────────────────┬──────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   File Tools    │  │   Git Tools     │  │   Test Tools    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## License

MIT
