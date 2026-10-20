"""The project memory file is written only when something changed, and a folder that can't be
written to doesn't stop interactive mode."""
import json
import os
import stat
from unittest.mock import MagicMock

import pytest

from agent.core import create_interactive_agent
from agent.memory import ProjectMemory
from agent.tool_system import tool_system


def start(folder):
    return create_interactive_agent(MagicMock(), tool_system, project_path=str(folder))


def test_starting_again_does_not_rewrite_the_file(tmp_path):
    (tmp_path / "src").mkdir()
    start(tmp_path)
    memory_file = tmp_path / ".agent-memory.json"
    saved = json.loads(memory_file.read_text())
    saved["updated_at"] = "2026-01-01T00:00:00"  # as if it was written long ago
    memory_file.write_text(json.dumps(saved))

    start(tmp_path)
    # Before: rewritten on every start, with "Last updated" set to now
    assert json.loads(memory_file.read_text())["updated_at"] == "2026-01-01T00:00:00"


def test_a_change_in_the_project_is_saved(tmp_path):
    start(tmp_path)
    (tmp_path / "tests").mkdir()
    agent = start(tmp_path)
    assert json.loads((tmp_path / ".agent-memory.json").read_text())["structure"]["test_dir"] == "tests"
    assert "- test_dir: tests" in agent.memory.get_context()


def test_update_tools_saves_only_new_values(tmp_path):
    memory = ProjectMemory(str(tmp_path))
    memory.update_tools({"test_command": "pytest -q"})
    memory.data["updated_at"] = "2026-01-01T00:00:00"
    memory.update_tools({"test_command": "pytest -q"})
    assert memory.data["updated_at"] == "2026-01-01T00:00:00"
    memory.update_tools({"test_command": "pytest"})
    assert memory.data["updated_at"] != "2026-01-01T00:00:00"
    assert json.loads((tmp_path / ".agent-memory.json").read_text())["tools"]["test_command"] == "pytest"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that read-only permissions apply to")
def test_read_only_folder_still_starts(tmp_path, capsys):
    (tmp_path / "src").mkdir()
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        # Before: PermissionError, and interactive mode exited before the first prompt
        agent = start(tmp_path)
    finally:
        tmp_path.chmod(stat.S_IRWXU)
    assert "could not save the project memory" in capsys.readouterr().out
    assert not (tmp_path / ".agent-memory.json").exists()
    # The layout is still known for this session
    assert "- src_dir: src" in agent.memory.get_context()


@pytest.mark.parametrize("content", ["[]", '"text"', '{"structure": 1}', "{not json"])
def test_a_broken_memory_file_starts_over(tmp_path, content):
    (tmp_path / ".agent-memory.json").write_text(content)
    (tmp_path / "src").mkdir()
    agent = start(tmp_path)
    assert agent.memory.data["structure"]["src_dir"] == "src"
