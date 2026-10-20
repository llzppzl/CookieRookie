"""agent/test_debug_demo.py - the debug-mode demo still has its bug, and the README describes it"""
import os
import shutil
import subprocess
import sys

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "debug-demo")


def run_app(folder):
    return subprocess.run([sys.executable, "app.py"], cwd=folder, capture_output=True, text=True, timeout=30)


def test_the_demo_crashes_as_the_readme_says():
    result = run_app(DEMO)
    assert result.returncode != 0
    assert "AttributeError: 'User' object has no attribute 'nmae'" in result.stderr
    readme = open(os.path.join(DEMO, "README.md"), encoding="utf-8").read()
    assert "AttributeError: 'User' object has no attribute 'nmae'" in readme


def test_fixing_the_typo_gives_the_expected_output(tmp_path):
    folder = tmp_path / "demo"
    shutil.copytree(DEMO, folder)
    user = folder / "user.py"
    user.write_text(user.read_text(encoding="utf-8").replace("self.nmae", "self.name"), encoding="utf-8")

    result = run_app(folder)
    assert result.returncode == 0
    assert result.stdout.strip() == "Hello, Ada!"
