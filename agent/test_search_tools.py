"""agent/test_search_tools.py - find_files and search_files look at the project's own files"""
from agent.tools import find_files, search_files


def make_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def login():\n    timeout = 5\n", encoding="utf-8")
    for folder in (".venv/lib/site-packages/pkg", "venv/lib", "node_modules/m", ".git/hooks", "src/__pycache__"):
        (tmp_path / folder).mkdir(parents=True)
    for i in range(60):
        (tmp_path / ".venv/lib/site-packages/pkg" / f"m{i}.py").write_text("timeout = 1\n", encoding="utf-8")
    (tmp_path / "venv/lib/v.py").write_text("timeout = 1\n", encoding="utf-8")
    (tmp_path / "node_modules/m/a.py").write_text("timeout = 1\n", encoding="utf-8")
    (tmp_path / ".git/hooks/h.py").write_text("timeout = 1\n", encoding="utf-8")
    (tmp_path / "src/__pycache__/app.py").write_text("timeout = 1\n", encoding="utf-8")
    return tmp_path


def test_find_files_skips_installed_packages_and_hidden_folders(tmp_path):
    project = make_project(tmp_path)
    result = find_files("*.py", path=str(project))
    assert result["matches"] == [str(project / "src" / "app.py")]
    assert result["count"] == 1


def test_search_files_skips_them_too(tmp_path):
    project = make_project(tmp_path)
    result = search_files("timeout", path=str(project))
    assert [(m["file"], m["line"]) for m in result["matches"]] == [(str(project / "src" / "app.py"), 2)]


def test_a_skipped_folder_can_still_be_searched_directly(tmp_path):
    project = make_project(tmp_path)
    assert find_files("*.py", path=str(project / "node_modules"))["count"] == 1


def test_path_patterns_and_regex_still_work(tmp_path):
    project = make_project(tmp_path)
    assert find_files("src/*.py", path=str(project))["count"] == 1
    assert find_files(r"^app\.py$", path=str(project), use_regex=True)["count"] == 1
    assert search_files(r"time\w+ = \d", path=str(project), use_regex=True)["count"] == 1
    assert search_files("timeout", path=str(project), file_glob="src/*.py")["count"] == 1


def test_files_that_are_not_text_are_skipped(tmp_path):
    (tmp_path / "data.py").write_bytes(b"\xff\xfe\x00timeout")
    (tmp_path / "ok.py").write_text("timeout = 1\n", encoding="utf-8")
    assert search_files("timeout", path=str(tmp_path))["count"] == 1
