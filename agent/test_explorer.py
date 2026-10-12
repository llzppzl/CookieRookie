"""agent/test_explorer.py"""
import pytest
import tempfile
import os
from agent.explorer import auto_detect_structure


class TestExplorer:
    def test_detect_python_project(self):
        """Detects a Python project"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"))
            os.makedirs(os.path.join(tmpdir, "tests"))

            structure = auto_detect_structure(tmpdir)
            assert structure["src_dir"] == "src"
            assert structure["test_dir"] == "tests"

    def test_detect_no_structure(self):
        """Detects an empty project"""
        with tempfile.TemporaryDirectory() as tmpdir:
            structure = auto_detect_structure(tmpdir)
            assert structure["src_dir"] is None
            assert structure["test_dir"] is None

    def test_detect_main_file(self):
        """Detects the main entry file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("")

            structure = auto_detect_structure(tmpdir)
            assert structure["main_file"] == "main.py"

    def test_priority_src_over_lib(self):
        """src wins over lib"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"))
            os.makedirs(os.path.join(tmpdir, "lib"))

            structure = auto_detect_structure(tmpdir)
            assert structure["src_dir"] == "src"

    def test_priority_tests_over_test(self):
        """tests wins over test"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            os.makedirs(os.path.join(tmpdir, "test"))

            structure = auto_detect_structure(tmpdir)
            assert structure["test_dir"] == "tests"
