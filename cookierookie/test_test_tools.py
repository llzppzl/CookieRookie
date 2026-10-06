"""cookierookie/test_test_tools.py"""
import pytest
import os
import tempfile
from cookierookie.test_tools import test_run, test_generate, _detect_framework


class TestTestTools:
    def test_detect_pytest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pytest.ini"), "w") as f:
                f.write("[pytest]\n")
            framework = _detect_framework(tmpdir)
            assert framework == "pytest"

    def test_detect_unittest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_sample.py")
            with open(test_file, "w") as f:
                f.write("import unittest\nclass TestSample(unittest.TestCase):\n    pass\n")
            framework = _detect_framework(tmpdir)
            assert framework == "unittest"

    def test_test_run_invalid_path(self):
        result = test_run(path="/nonexistent/path/xyz")
        assert result["success"] is False
        assert "error" in result

    def test_test_generate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "calculator.py")
            with open(source, "w") as f:
                f.write("def add(a, b): return a + b\n")
            result = test_generate(source=source)
            assert result["success"] is True
            assert result["source"] == source


# ---------- running a project's tests ----------

import sys

from cookierookie import test_tools

PASSING = "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
FAILING = "from calc import add\n\ndef test_add_wrong():\n    assert add(1, 2) == 4\n"


def make_project(root, tests):
    """A project with calc.py and the test files in tests ({relative path: source})"""
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    for name, source in tests.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)


@pytest.fixture
def python_with_pytest(monkeypatch):
    """Run the project's tests with the Python running these tests, which has pytest"""
    monkeypatch.setattr(test_tools, "_python", lambda path: sys.executable)


def test_test_run_finds_tests_in_a_tests_directory(tmp_path, python_with_pytest):
    make_project(tmp_path, {"tests/test_calc.py": PASSING})

    result = test_run(path=str(tmp_path))

    assert result["success"] is True, result
    assert result["passed"] == 1


def test_test_run_reports_failures(tmp_path, python_with_pytest):
    make_project(tmp_path, {"test_calc.py": PASSING, "test_wrong.py": FAILING})

    result = test_run(path=str(tmp_path))

    assert result["success"] is False
    assert (result["passed"], result["failed"]) == (1, 1)
    assert "assert 3 == 4" in result["stdout"]


def test_test_run_expands_a_glob(tmp_path, python_with_pytest):
    make_project(tmp_path, {"tests/test_calc.py": PASSING, "tests/test_wrong.py": FAILING})

    result = test_run(path=str(tmp_path), pattern="tests/test_c*.py")

    assert result["success"] is True, result
    assert (result["passed"], result["failed"]) == (1, 0)


def test_test_run_runs_one_file(tmp_path, python_with_pytest):
    make_project(tmp_path, {"tests/test_calc.py": PASSING, "tests/test_wrong.py": FAILING})

    result = test_run(path=str(tmp_path), pattern="tests/test_wrong.py")

    assert (result["passed"], result["failed"]) == (0, 1)


def test_test_run_runs_unittest_tests(tmp_path, python_with_pytest):
    (tmp_path / "test_calc.py").write_text(
        "import unittest\n\nclass TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(1 + 2, 3)\n")

    result = test_run(path=str(tmp_path))

    assert result["framework"] == "unittest"
    assert result["success"] is True, result
    assert "Ran 1 test" in result["stderr"]


def test_test_run_says_when_a_glob_matches_nothing(tmp_path):
    result = test_run(path=str(tmp_path), pattern="test_*.py", framework="pytest")

    assert result["success"] is False
    assert "No files match test_*.py" in result["error"]


def test_test_run_does_not_pass_an_option_as_the_pattern(tmp_path):
    result = test_run(path=str(tmp_path), pattern="-p some_plugin")

    assert result["success"] is False
    assert "not an option" in result["error"]


def test_test_run_says_which_program_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(test_tools, "_python", lambda path: "no-such-python")

    result = test_run(path=str(tmp_path), framework="pytest")

    assert result["error"] == "no-such-python was not found. Is pytest installed?"


def test_tests_run_with_the_projects_virtualenv(tmp_path):
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")

    assert test_tools._python(str(tmp_path)) == str(python)


def test_without_python_on_path_tests_run_with_python3_or_this_python(tmp_path, monkeypatch):
    # macOS has python3 but no python
    monkeypatch.setattr(test_tools.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    assert test_tools._python(str(tmp_path)) == "/usr/bin/python3"

    monkeypatch.setattr(test_tools.shutil, "which", lambda name: None)
    assert test_tools._python(str(tmp_path)) == sys.executable
