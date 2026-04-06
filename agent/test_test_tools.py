"""agent/test_test_tools.py"""
import pytest
import os
import tempfile
from agent.test_tools import test_run, test_generate, _detect_framework


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
