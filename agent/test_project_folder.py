"""edit_file and write_file only change files inside the folder CookieRookie runs in."""
import os

import pytest

from agent import tools
from agent.tools import edit_file, write_file


@pytest.fixture
def project(tmp_path, monkeypatch):
    """tmp_path/project is the working directory, tmp_path/outside is not inside it."""
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    monkeypatch.chdir(root)
    # Undo conftest's allowance for pytest's temporary folders, so "outside" really is outside
    monkeypatch.setattr(tools, "project_dirs", lambda: [os.getcwd()])
    return root


def test_writes_and_edits_inside_the_project_work(project):
    assert write_file("app.py", "x = 1\n")["success"] is True
    assert edit_file("app.py", line=1, new_string="x = 2")["success"] is True
    assert (project / "app.py").read_text() == "x = 2\n"

    (project / "src").mkdir()
    assert write_file(str(project / "src" / "b.py"), "b = 1\n")["success"] is True


@pytest.mark.parametrize("path", ["../outside/a.py", "{tmp}/outside/a.py", "src/../../outside/a.py"])
def test_write_outside_the_project_is_refused(project, tmp_path, path):
    result = write_file(path.format(tmp=tmp_path), "x = 1\n")

    assert result["success"] is False
    assert "outside the project folder" in result["error"]
    assert not (tmp_path / "outside" / "a.py").exists()


def test_edit_outside_the_project_is_refused(project, tmp_path):
    target = tmp_path / "outside" / "settings.py"
    target.write_text("DEBUG = False\n")

    result = edit_file(path=str(target), old_string="False", new_string="True")

    assert result["success"] is False
    assert target.read_text() == "DEBUG = False\n"


def test_symlink_pointing_outside_is_refused(project, tmp_path):
    target = tmp_path / "outside" / "real.py"
    target.write_text("x = 1\n")
    try:
        os.symlink(target, project / "link.py")
    except OSError:
        pytest.skip("symlinks are not available here")

    assert write_file("link.py", "x = 2\n")["success"] is False
    assert target.read_text() == "x = 1\n"


def test_missing_path_still_gives_the_tools_own_error(project):
    with pytest.raises(TypeError, match="path"):
        write_file(content="x")


def test_both_modes_use_the_guarded_tools(project, tmp_path):
    """Interactive mode calls the tools through tool_system, debug mode through register_tools()."""
    from agent.tool_system import tool_system
    outside = str(tmp_path / "outside" / "x.py")

    debug_tools = tools.register_tools()
    assert debug_tools["write_file"](path=outside, content="x")["success"] is False
    assert tool_system.get("write_file").fn(path=outside, content="x")["success"] is False
    assert tool_system.get("edit_file").fn(path=outside, line=1, new_string="x")["success"] is False
    assert not os.path.exists(outside)
