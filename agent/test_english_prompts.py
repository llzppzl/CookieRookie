"""What the model reads is in English and names every tool's arguments."""
from unittest.mock import MagicMock

from agent.core import SYSTEM_PROMPT, InteractiveAgent, _describe_args
from agent.tool_system import ToolSystem
from agent import tools

import main


def has_cjk(text: str) -> bool:
    return any(0x4e00 <= ord(c) <= 0x9fff for c in text)


def base_tool_system() -> ToolSystem:
    ts = ToolSystem()
    ts.register("read_file", tools.read_file)
    ts.register("edit_file", tools.edit_file, confirmable=True)
    ts.register("exec", tools.exec, confirmable=True, description="run a shell command")
    return ts


def test_describe_args():
    assert _describe_args(tools.read_file) == "path, offset=1, limit=100"
    assert _describe_args(lambda *a, **kw: None) == "*a, **kw"


def test_prompts_are_english():
    assert not has_cjk(SYSTEM_PROMPT)
    assert not has_cjk(InteractiveAgent(MagicMock(), base_tool_system())._build_system_prompt())


def test_interactive_prompt_lists_arguments():
    prompt = InteractiveAgent(MagicMock(), base_tool_system())._build_system_prompt()
    assert "- read_file(path, offset=1, limit=100)\n" in prompt
    assert "- edit_file(path, line=None, new_string=None, old_string=None) [asks the user first]" in prompt
    assert "- exec(command, workdir=None, timeout=30) [asks the user first]: run a shell command" in prompt


def test_interactive_prompt_has_no_missing_tools():
    # plan() and execute_plan() are agent methods, not tools the model can call
    prompt = InteractiveAgent.SYSTEM_PROMPT
    assert "plan(task)" not in prompt and "execute_plan" not in prompt


def test_confirmation_box_is_english(capsys):
    agent = InteractiveAgent(MagicMock(), base_tool_system())
    agent.pending_action = {"thought": "run it", "tool_name": "exec", "tool_args": {"command": "ls"}}
    agent._show_pending_action()
    out = capsys.readouterr().out
    assert not has_cjk(out)
    assert "/confirm" in out and "/reject" in out and "/edit" in out


def test_history_sent_to_the_model_is_english():
    client = main.LLMClient("key")
    history = [
        {"iteration": 1, "thought": "read", "action": {"tool": "read_file", "args": {"path": "a.py"}},
         "result": {"success": True, "lines": "1-2", "total": 2, "content": "x" * 3000}},
        {"iteration": 2, "thought": "run", "action": {"tool": "exec", "args": {"command": "ls"}},
         "result": {"success": True, "returncode": 0, "stdout": "y" * 1000, "stderr": ""}},
        {"iteration": 3, "thought": "edit", "action": {"tool": "edit_file", "args": {"path": "a.py", "line": 1, "new_string": "z" * 80}},
         "result": {"success": True, "path": "a.py", "line": 1, "mode": "line", "new_line": "z"}},
        {"iteration": 4, "thought": "search", "action": {"tool": "search_files", "args": {"pattern": "x"}},
         "result": {"success": True, "count": 7, "matches": [{"file": "a.py", "line": 1, "content": "x"}] * 7}},
        {"iteration": 5, "thought": "find", "action": {"tool": "find_files", "args": {"pattern": "*.py"}},
         "result": {"success": True, "count": 12, "matches": ["a.py"] * 12}},
        {"iteration": 6, "thought": "other", "action": {"tool": "test_generate", "args": {"source": "a.py"}},
         "result": {"success": True, "source_content": "q" * 1000}},
        {"iteration": 7, "thought": "fail", "action": {"tool": "read_file", "args": {"path": "b.py"}},
         "result": {"success": False, "error": "File not found: b.py"}},
    ]
    message = client._build_user_message({"bug_report": "bug", "history": history})
    assert not has_cjk(message)
    assert "### Step 1" in message
    assert "Result: failed - File not found: b.py" in message
