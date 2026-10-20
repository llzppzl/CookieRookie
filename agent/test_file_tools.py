"""read_file, edit_file and write_file refuse unclear requests instead of doing the wrong thing."""
from agent.tools import read_file, edit_file, write_file


def make(tmp_path, text="x = 1\ny = 2\nx = 1\n"):
    path = tmp_path / "a.py"
    path.write_text(text)
    return path


def test_write_file_creates_missing_folders(tmp_path):
    target = tmp_path / "tests" / "unit" / "test_a.py"
    result = write_file(str(target), "def test_a():\n    pass\n")
    assert result["success"] is True
    assert target.read_text() == "def test_a():\n    pass\n"


def test_write_file_in_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert write_file("b.py", "b = 1\n")["success"] is True
    assert (tmp_path / "b.py").read_text() == "b = 1\n"


def test_edit_refuses_old_string_that_matches_twice(tmp_path):
    path = make(tmp_path)
    result = edit_file(str(path), old_string="x = 1", new_string="x = 3")
    assert result["success"] is False
    assert "2 times" in result["error"]
    assert path.read_text() == "x = 1\ny = 2\nx = 1\n"


def test_edit_old_string_that_matches_once(tmp_path):
    path = make(tmp_path)
    assert edit_file(str(path), old_string="y = 2", new_string="y = 5")["success"] is True
    assert path.read_text() == "x = 1\ny = 5\nx = 1\n"


def test_edit_without_new_string_is_a_clear_error(tmp_path):
    path = make(tmp_path)
    for kwargs in ({"line": 1}, {"old_string": "y = 2"}):
        result = edit_file(str(path), **kwargs)
        assert result["success"] is False
        assert "new_string is missing" in result["error"]
    assert path.read_text() == "x = 1\ny = 2\nx = 1\n"


def test_edit_takes_line_number_as_text(tmp_path):
    path = make(tmp_path)
    assert edit_file(str(path), line="2", new_string="y = 9")["success"] is True
    assert path.read_text() == "x = 1\ny = 9\nx = 1\n"


def test_edit_empty_new_string_is_allowed(tmp_path):
    path = make(tmp_path)
    assert edit_file(str(path), old_string="y = 2\n", new_string="")["success"] is True
    assert path.read_text() == "x = 1\nx = 1\n"


def test_read_refuses_offset_below_one(tmp_path):
    path = make(tmp_path)
    for offset in (0, -1):
        result = read_file(str(path), offset=offset)
        assert result["success"] is False
        assert "at least 1" in result["error"]


def test_read_refuses_limit_below_one(tmp_path):
    result = read_file(str(make(tmp_path)), limit=0)
    assert result["success"] is False


def test_read_takes_numbers_as_text(tmp_path):
    result = read_file(str(make(tmp_path)), offset="2", limit="1")
    assert result["success"] is True
    assert result["content"] == "y = 2\n"
    assert result["lines"] == "2-2"
