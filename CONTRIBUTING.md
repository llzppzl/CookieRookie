# Contributing to CookieRookie

## Set up

```bash
git clone https://github.com/llzppzl/CookieRookie.git
cd CookieRookie
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
```

You only need an API key (see `.env.example`) to run the agent itself, not for the tests.

## Run the tests

```bash
.venv/bin/python -m pytest agent
```

The tests don't call any API: they use scripted fake LLM replies. Add a test for every bug you fix and every feature you add.

## Where things are

| File | What it does |
|------|--------------|
| `main.py` | Command line, `.env` config, `LLMClient` (the HTTP call to the Messages API and parsing of the model's reply) |
| `agent/core.py` | `DebugAgent` and `InteractiveAgent`: the loop, confirmations, plans |
| `agent/tool_system.py` | `ToolSystem`: the tool registry and the `confirmable` flag |
| `agent/tools.py` | File and shell tools, and their registration |
| `agent/git_tools.py`, `agent/test_tools.py` | git tools; running and generating tests |
| `agent/memory.py`, `agent/explorer.py` | Project memory (`.agent-memory.json`) |

## Adding a tool

1. Write the function so it returns a dict with `success` and, on failure, `error`. Don't raise for expected failures.
2. Register it in `register_base_tools()` in `agent/tools.py` with a short description.
3. Pass `confirmable=True` if the tool changes files, runs commands or has any other side effect. The user must see and approve it first.
4. Add tests, and update the tool table in `README.md` and `SECURITY.md`.

## Pull requests

- One topic per pull request, with a description of what was wrong and what changed.
- Code, comments, docs, commit messages and pull requests are in English.
- Make sure `python -m pytest agent` passes.
