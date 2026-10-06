# CookieRookie

An autonomous AI coding agent that understands your codebase, writes code, generates tests, and helps you build features — with you in control.

## Features

- 🤖 **LLM-Powered** - Uses any Anthropic-compatible API (Minimax, DeepSeek, Kimi, etc.)
- 🛠️ **Tool Execution** - Read, edit, write files; execute commands; run tests
- 🔧 **Auto-Debug** - Automatically reads, analyzes, and fixes bugs
- 📋 **Plans** - `/plan` shows the steps before anything runs; leave some out or have them changed, then run it
- 💾 **Project Memory** - Learns your project structure automatically
- 🔄 **Interactive Confirmation** - You confirm dangerous actions before execution

## Quick Start

Requires Python 3.9+.

```bash
# 1. Install the `cookierookie` command
pip install git+https://github.com/llzppzl/CookieRookie.git

# 2. Set your API key once (any provider in the table below)
mkdir -p ~/.config/cookierookie
cat > ~/.config/cookierookie/.env <<'ENV'
ANTHROPIC_API_KEY=your-api-key-here
MODEL_ID=MiniMax-M2.5
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ENV

# 3. Go to your own project and start
cd path/to/your-project
cookierookie
```

CookieRookie works on the directory you start it in. Reading and searching run on their own. Before any file edit or shell command, in either mode, it shows you the change and waits for your answer.

## Two Modes

### Interactive Mode (Recommended)

```bash
cookierookie
> help  # Show available commands
> 帮我写一个计算器模块
> 为 src/calculator.py 生成测试
> 修复登录功能的 bug
> /plan add a divide function to calc.py, with a test
```

### Debug Mode

```bash
cookierookie "Your bug description here"
```

Before each edit or command, debug mode shows it and asks:

```
Edit app/user.py, line 19:
- return user["name"]
+ return user.get("name", "")
Allow? [y]es / [N]o / [a]ll / [q]uit, or tell the agent what to do instead:
```

`a` allows everything for the rest of the run. Pressing Enter or typing `n` declines. You can also type what to do instead, and the agent gets your words as feedback. To skip the questions, for example in a script, run `cookierookie --yes "..."`.

## Configuration

CookieRookie reads these settings, highest priority first:

1. Environment variables (`ANTHROPIC_API_KEY`, `MODEL_ID`, `ANTHROPIC_BASE_URL`)
2. `.env` in the directory you run it from
3. `~/.config/cookierookie/.env`
4. `.env` in the repository root (only when running from a source checkout)

See [.env.example](.env.example) for all options.

`MAX_TOKENS` (default 8192) limits each model reply. If CookieRookie reports that a reply was cut off, raise it.

### Supported Models

| Provider | Model ID | Base URL |
|----------|----------|----------|
| Minimax | `MiniMax-M2.5` | `https://api.minimax.io/anthropic` |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/anthropic` |
| Kimi | `kimi-k2.5` | `https://api.moonshot.ai/anthropic` |
| GLM | `glm-5` | `https://api.z.ai/api/anthropic` |
| Anthropic | `claude-sonnet-4-6` | `https://api.anthropic.com` |

CookieRookie gives the model its tools through the API's tool use (function calling), so the model has to support it. The Anthropic-compatible endpoints of the providers above do.

### Running from source

```bash
git clone https://github.com/llzppzl/CookieRookie.git
cd CookieRookie
pip install -e .
python -m pytest
```

`python main.py` still works for existing setups.

## Interactive Commands

| Command | Description |
|---------|-------------|
| `help` | Show help information |
| `/confirm` | Run the pending edit or command. With none waiting, run the plan |
| `/reject [what to do instead]` | Don't run it. With a reason, the agent tries another way on the same task; without one, the task stops. For a plan: change it as you say, or without a reason drop it |
| `/edit key=value ...` | Change some of the pending action's arguments, then run it. Quote values with spaces: `/edit command="python -m pytest -q"` |
| `/status` | Show what is waiting: the pending action and the plan |
| `/plan <task>` | Make a plan for the task. Nothing runs until you `/confirm` it |
| `/plan` | Show the plan again |
| `/skip N` | Leave step N out of the plan |
| `exit`, `quit` | Exit interactive mode |

## How It Works

### Each Step

1. CookieRookie sends the model your task, what has happened so far, and the tools it can call.
2. The model answers with one tool call, or with a final answer when the task is done.
3. Reading and searching run right away. Edits and commands are shown to you first.
4. The result goes into the history for the next step.

Tool calls arrive as JSON, so file content with quotes, backslashes or many lines is written exactly as the model wrote it.

### Plans

A task you type starts right away. To see the steps first, use `/plan <task>`:

1. The model writes a plan. Nothing runs, and the model gets no tools for it.
2. You read it. `/skip N` leaves step N out, `/reject <what to change>` gets a new plan with your change, and `/reject` alone drops it.
3. `/confirm` hands the plan to the agent, which carries it out step by step. Each edit and command in it still waits for your `/confirm`, as usual. If what the agent finds shows that a step is wrong, it does what the task needs instead and says why.

### Available Tools

| Category | Run on their own | Ask you first |
|----------|------------------|---------------|
| File | read_file, search_files, find_files | edit_file, write_file |
| Execute | | exec |
| Test | test_run, test_generate | |
| Git | git_status, git_diff, git_log, git_branch | git_commit, git_checkout |

All tools work in the directory you started CookieRookie in. `test_run` finds the tests itself and uses the project's `.venv` or `venv` if there is one. Debug mode uses the file tools and `exec`.

## Project Structure

```
CookieRookie/
├── cookierookie/
│   ├── __init__.py
│   ├── cli.py               # Command-line entry point, LLM client, config loading
│   ├── core.py              # Agent logic (DebugAgent, InteractiveAgent)
│   ├── tools.py             # Base file tools
│   ├── tool_system.py       # Plugin-based tool registry
│   ├── memory.py            # Project memory
│   ├── explorer.py          # Auto-detect project structure
│   ├── git_tools.py         # Git operations
│   ├── test_tools.py        # Test execution & generation
│   └── test_*.py            # Tests
├── docs/superpowers/        # Design specs and implementation plans
├── main.py                  # Backward-compatible entry point
├── pyproject.toml
└── .env.example
```

## Usage Examples

### Write Code

```bash
cookierookie
> 帮我写一个用户管理模块
# The agent looks at the project, then shows each file it wants to write and waits
> /confirm
```

### Generate Tests

```bash
cookierookie
> 为 src/calculator.py 生成测试
# Agent creates test file and runs it
```

### Debug

```bash
cookierookie "calculator.py returns wrong result when dividing by zero"
```

### Plan Mode

```
cookierookie
> /plan add a divide function to calc.py, with a test
Plan: Add divide() to calc.py, with a test

1. [read_file] Read calc.py
2. [edit_file] Add divide(a, b)  (asks you first)
3. [write_file] Create tests/test_divide.py  (asks you first)
4. [test_run] Run tests/test_divide.py

/confirm to run it | /skip N to leave out step N | /reject [what to change]
> /reject it should raise ZeroDivisionError for 0
Plan: Add divide() to calc.py, raising ZeroDivisionError for 0, with tests

1. [read_file] Read calc.py
2. [edit_file] Add divide(a, b), raising ZeroDivisionError when b is 0  (asks you first)
3. [write_file] Create tests/test_divide.py, with a test for b = 0  (asks you first)
4. [git_status] Show what changed
5. [test_run] Run tests/test_divide.py

/confirm to run it | /skip N to leave out step N | /reject [what to change]
> /skip 4
> /confirm
# Reads calc.py, shows the edit and waits for /confirm, shows the test file and waits, then runs the tests
```

## Extending

### Adding New Tools

1. Implement the tool function in `cookierookie/tools.py`:

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
    confirmable=True,  # True for tools that change files or run commands: the user is asked first
    description="What the tool does, for the model",
    args_schema={  # optional
        "type": "object",
        "properties": {"param1": {"type": "string", "description": "What param1 is"}},
        "required": ["param1"],
    },
)
```

The model sees the description and the argument schema. Without `args_schema`, the schema is built from the function's signature: parameters without a default are required, and their types come from the annotations. Without `description`, the first line of the docstring is used.

### Changing System Prompt

Edit `SYSTEM_PROMPT` (debug mode) or `InteractiveAgent.SYSTEM_PROMPT` (interactive mode) in `cookierookie/core.py` to customize agent behavior.

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
