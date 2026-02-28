# Debug Agent

An autonomous AI agent that automatically locates and fixes code bugs through LLM reasoning and tool execution.

## Features

- 🤖 **LLM-Powered** - Uses any Anthropic-compatible API (Minimax, DeepSeek, Kimi, etc.)
- 🔧 **Auto-Debug** - Automatically reads, analyzes, and fixes bugs
- 🛠️ **Tool Execution** - Execute shell commands, edit files, search code
- 🔄 **Iterative** - Keeps trying until bug is fixed or max iterations reached

## Quick Start

```bash
# 1. Clone and install dependencies
git clone https://github.com/your-repo/debugAgent.git
cd debugAgent
pip install -r requirements.txt

# 2. Copy and configure environment
copy .env.example .env
# Edit .env with your API key

# 3. Run with a bug description
python main.py "Your bug description here"
```

## Configuration

Create a `.env` file (see `.env.example`):

```bash
# Required: Your API key (Minimax, Anthropic, DeepSeek, Kimi, etc.)
ANTHROPIC_API_KEY=your-api-key-here

# Model ID (default: MiniMax-M2.5)
MODEL_ID=MiniMax-M2.5

# API endpoint (default: Minimax)
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
```

### Supported Models

| Provider | Model ID | Base URL |
|----------|----------|----------|
| Minimax | `MiniMax-M2.5` | `https://api.minimax.io/anthropic` |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/anthropic` |
| Kimi | `kimi-k2.5` | `https://api.moonshot.ai/anthropic` |
| GLM | `glm-5` | `https://api.z.ai/api/anthropic` |
| Anthropic | `claude-sonnet-4-6` | `https://api.anthropic.com` |

## Project Structure

```
debugAgent/
├── agent/
│   ├── core.py          # Agent loop logic
│   ├── tools.py         # Tool implementations
│   └── __init__.py
├── examples/
│   ├── calculator.py    # Test case with bugs
│   └── user_manager.py  # Another test case
├── main.py              # Entry point
├── .env.example         # Configuration template
└── requirements.txt     # Python dependencies
```

## How It Works

1. **Analysis** - LLM analyzes the bug report
2. **Action** - Agent decides next tool to use (read, edit, exec, search)
3. **Execution** - Tool runs and returns result
4. **Verification** - Agent checks if bug is fixed
5. **Loop** - Repeats until fixed or max iterations (default: 10)

## Usage Examples

```bash
# Debug a Python file
python main.py "calculator.py returns wrong result when dividing by zero"

# Debug a JavaScript file
python main.py "The login button doesn't respond on mobile"

# Debug with environment variable
set DEBUG_BUG_REPORT="Your bug description"
python main.py
```

## Extending

### Adding New Tools

Edit `agent/tools.py` to add custom tools:

```python
def my_custom_tool(param1: str) """Your -> dict:
    tool description"""
    # Tool implementation
    return {"success": True, "result": "..."}

# Register in register_tools()
tools["my_tool"] = my_custom_tool
```

### Changing System Prompt

Edit `SYSTEM_PROMPT` in `agent/core.py` to customize agent behavior.

## License

MIT
