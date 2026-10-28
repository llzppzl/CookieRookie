"""agent/test_read_line_numbers.py - file contents in the history come with their line numbers"""
import main


def history_text(result, args=None):
    context = {"bug_report": "bug", "history": [{
        "action": {"tool": "read_file", "args": args or {"path": "app.py"}},
        "result": result, "thought": "read it", "iteration": 1}]}
    return main.LLMClient("key")._build_user_message(context)


def test_lines_are_numbered_from_the_offset():
    text = history_text({"success": True, "content": "def div(a, b):\n    return a / b\n",
                         "lines": "10-11", "total": 30})
    assert "  10 | def div(a, b):\n" in text
    assert "  11 |     return a / b\n" in text
    assert "not part of the file" in text


def test_a_file_read_from_the_start_begins_at_line_1():
    text = history_text({"success": True, "content": "a = 1\nb = 2", "lines": "1-2", "total": 2})
    assert "   1 | a = 1\n   2 | b = 2" in text


def test_empty_file_shows_no_numbers():
    text = history_text({"success": True, "content": "", "lines": "1-0", "total": 0})
    assert " | " not in text
    assert "not part of the file" not in text


def test_reading_an_empty_file_works_and_says_it_is_empty(tmp_path, monkeypatch):
    # It used to fail with "Offset 1 beyond file length 0"
    from agent.tools import read_file
    monkeypatch.chdir(tmp_path)
    (tmp_path / "__init__.py").write_text("")
    result = read_file("__init__.py")
    assert result["success"] is True
    assert result["content"] == "" and result["total"] == 0
    assert "the file is empty" in history_text(result, {"path": "__init__.py"})
    # Past the end of an empty file is still an error
    assert read_file("__init__.py", offset=2)["success"] is False


def test_line_numbers_match_what_edit_file_changes(tmp_path, monkeypatch):
    # The number shown next to a line is the line=N that edit_file replaces
    from agent.tools import read_file, edit_file
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
    result = read_file("app.py", offset=2, limit=2)
    shown = history_text(result)
    number = int(next(line for line in shown.splitlines() if line.endswith("| y = 2")).split("|")[0])
    edit_file("app.py", line=number, new_string="y = 20")
    assert (tmp_path / "app.py").read_text() == "x = 1\ny = 20\nz = 3\n"
