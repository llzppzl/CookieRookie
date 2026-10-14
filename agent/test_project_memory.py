"""agent/test_project_memory.py - interactive mode remembers the project it is started in"""
import builtins
import os
from unittest.mock import MagicMock

import main
from agent import core
from agent.core import create_interactive_agent
from agent.tool_system import tool_system


def test_create_interactive_agent_passes_project_path(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    agent = create_interactive_agent(MagicMock(), tool_system, project_path=str(tmp_path))
    assert agent.memory is not None
    assert agent.memory.data["structure"]["src_dir"] == "src"
    assert (tmp_path / ".agent-memory.json").exists()
    context = agent._build_initial_context("add a feature")
    assert "- src_dir: src" in context["memory"]
    assert "- test_dir: tests" in context["memory"]


def test_without_project_path_there_is_no_memory():
    assert create_interactive_agent(MagicMock(), tool_system).memory is None


def test_interactive_mode_uses_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real_config = main.load_config()
    monkeypatch.setattr(main, "load_config", lambda: {**real_config, "api_key": "test-key"})
    created = {}
    real_create = core.create_interactive_agent

    def spy(*args, **kwargs):
        created["agent"] = real_create(*args, **kwargs)
        return created["agent"]

    monkeypatch.setattr(core, "create_interactive_agent", spy)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "exit")
    main.interactive_main()

    agent = created["agent"]
    assert agent.project_path == os.getcwd()
    assert agent.memory is not None
    assert (tmp_path / ".agent-memory.json").exists()


def test_memory_file_is_not_committed_to_the_users_repo(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "app.py").write_text("print(1)\n")
    agent = create_interactive_agent(MagicMock(), tool_system, project_path=str(tmp_path))
    agent.memory.update_tools({"test_command": "pytest -q"})  # a second save adds no second line

    exclude = (tmp_path / ".git" / "info" / "exclude").read_text()
    assert exclude.count("/.agent-memory.json") == 1
    # What git_commit stages when it is given no files
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    staged = subprocess.run(["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, check=True).stdout.split()
    assert staged == ["app.py"]


def test_memory_outside_a_git_repo_creates_no_git_folder(tmp_path):
    create_interactive_agent(MagicMock(), tool_system, project_path=str(tmp_path))
    assert (tmp_path / ".agent-memory.json").exists()
    assert not (tmp_path / ".git").exists()


def test_memory_text_is_english(tmp_path):
    (tmp_path / "tests").mkdir()
    agent = create_interactive_agent(MagicMock(), tool_system, project_path=str(tmp_path))
    agent.memory.update_tools({"test_command": "pytest -q"})
    text = agent.memory.get_context()
    assert text.startswith("## Project memory")
    assert "### Project structure" in text
    assert "### Commands\n- test_command: pytest -q" in text
    assert "Last updated:" in text
    assert not any(0x4e00 <= ord(c) <= 0x9fff for c in text)
