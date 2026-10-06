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

CookieRookie works on the directory you start it in. Reading and searching run automatically; editing files and running commands wait for your `/confirm`.

## Two Modes

### Interactive Mode (Recommended)

```bash
cookierookie
> help  # Show available commands
> 帮我写一个计算器模块
> 为 src/calculator.py 生成测试
> 修复登录功能的 bug
```

### Debug Mode

```bash
cookierookie "Your bug description here"
```

## Configuration

CookieRookie reads these settings, highest priority first:

1. Environment variables (`ANTHROPIC_API_KEY`, `MODEL_ID`, `ANTHROPIC_BASE_URL`)
2. `.env` in the directory you run it from
3. `~/.config/cookierookie/.env`
4. `.env` in the repository root (only when running from a source checkout)

See [.env.example](.env.example) for all options.

### Supported Models

| Provider | Model ID | Base URL |
|----------|----------|----------|
| Minimax | `MiniMax-M2.5` | `https://api.minimax.io/anthropic` |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/anthropic` |
| Kimi | `kimi-k2.5` | `https://api.moonshot.ai/anthropic` |
| GLM | `glm-5` | `https://api.z.ai/api/anthropic` |
| Anthropic | `claude-sonnet-4-6` | `https://api.anthropic.com` |

### Running from source

```bash
git clone https://github.com/llzppzl/CookieRookie.git
cd CookieRookie
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip   # installing with -e needs pip 21.3 or newer
pip install -e . pytest
python -m pytest
```

`python main.py` still works for existing setups.

## Interactive Commands

| Command | Description |
|---------|-------------|
| `help` | Show help information |
| `/confirm` | Confirm and execute pending action |
| `/reject` | Reject and ask agent to replan |
| `/edit key=value` | Modify action parameters |
| `/status` | Show pending action status |
| `/plan` | View current execution plan |
| `/skip N` | Skip step N in the plan |
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
# Agent plans and asks for confirmation
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

```bash
cookierookie
> 帮我重构登录模块，添加测试

## 执行计划

1. [read_file] 读取 src/auth.py
2. [git_status] 查看当前状态
3. [write_file] 创建 tests/test_auth.py
4. [edit_file] 重构 login() 函数
5. [test_run] 运行测试验证

> /confirm
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
    confirmable=True,  # Set True for dangerous operations
    description="Description for LLM"
)
```

### Changing System Prompt

Edit `SYSTEM_PROMPT` in `cookierookie/core.py` to customize agent behavior.

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
