"""
Test Tools - run and generate tests
"""

import glob
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

from .tools import write_file

# Tell pytest not to collect functions in this module as tests
__test__ = False


def _detect_framework(path: str = ".") -> str:
    """Detect the test framework

    Looks at pytest.ini, pyproject.toml and the content of test_*.py

    Args:
        path: project path

    Returns:
        Framework name: pytest, unittest, jest, go
    """
    # Check pytest.ini
    pytest_ini = os.path.join(path, "pytest.ini")
    if os.path.exists(pytest_ini):
        with open(pytest_ini, "r", encoding="utf-8") as f:
            content = f.read()
            if "[pytest]" in content:
                return "pytest"

    # Check pyproject.toml
    pyproject = os.path.join(path, "pyproject.toml")
    if os.path.exists(pyproject):
        with open(pyproject, "r", encoding="utf-8") as f:
            content = f.read()
            if "pytest" in content:
                return "pytest"

    # Check the content of test_*.py files
    test_pattern = os.path.join(path, "test_*.py")
    for test_file in glob.glob(test_pattern):
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            if "unittest.TestCase" in content or "from unittest import" in content:
                return "unittest"
            if "jest" in content.lower():
                return "jest"

    # Check go.mod (go test)
    go_mod = os.path.join(path, "go.mod")
    if os.path.exists(go_mod):
        return "go"

    # Check package.json (jest)
    package_json = os.path.join(path, "package.json")
    if os.path.exists(package_json):
        with open(package_json, "r", encoding="utf-8") as f:
            content = f.read()
            if "jest" in content:
                return "jest"

    # Default to pytest
    return "pytest"


def _parse_passed(output: str) -> int:
    """Number of passed tests in the test output"""
    # pytest: "5 passed"
    match = re.search(r"(\d+)\s+passed", output)
    if match:
        return int(match.group(1))
    return 0


def _parse_failed(output: str) -> int:
    """Number of failed tests in the test output"""
    # pytest: "2 failed"
    match = re.search(r"(\d+)\s+failed", output)
    if match:
        return int(match.group(1))
    return 0


def _parse_errors(output: str) -> int:
    """Number of tests with errors in the test output"""
    # pytest: "1 error"
    match = re.search(r"(\d+)\s+error", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # unittest: "ERROR"
    if "ERROR" in output:
        errors = re.findall(r"ERROR", output)
        return len(errors)
    return 0


def _python(path: str) -> str:
    """The Python to run a project's tests with: the project's virtualenv (.venv or venv) if it
    has one, else python or python3 on PATH, else the Python running CookieRookie.
    macOS has no "python" command, only python3."""
    for venv in (".venv", "venv"):
        for exe in (os.path.join("bin", "python"), os.path.join("Scripts", "python.exe")):
            candidate = os.path.join(path, venv, exe)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return shutil.which("python") or shutil.which("python3") or sys.executable


def _test_targets(path: str, pattern: Optional[str]) -> List[str]:
    """The test files to pass the runner: none (it finds the tests itself), the file or directory
    in pattern, or the files a glob in pattern matches.

    The command runs without a shell, so a glob like test_*.py has to be expanded here.
    Passed as is, pytest looks for a file literally named "test_*.py" and runs nothing.
    """
    if not pattern:
        return []
    if not any(c in pattern for c in "*?["):
        return [pattern]
    matches = sorted(glob.glob(os.path.join(path, pattern), recursive=True))
    return [os.path.relpath(match, path) for match in matches]


def _test_command(path: str, pattern: Optional[str], framework: str):
    """The command test_run would run, as (cmd, framework, error): cmd is None when error says
    why nothing can run."""
    if not os.path.isdir(path):
        return None, framework, f"Directory not found: {path}"

    # The pattern goes on the command line, so it must not be read as an option (-p loads a plugin)
    if pattern and pattern.startswith("-"):
        return None, framework, f"pattern must be a file, directory or glob, not an option: {pattern}"

    # Detect the framework
    if framework == "auto":
        framework = _detect_framework(path)

    # Before (kept for comparison): the pattern went to pytest as is. No shell expanded test_*.py,
    # so pytest looked for a file of that name and ran nothing
    # cmd = ["python", "-m", "pytest", pattern, "-v"]
    if framework in ("pytest", "unittest"):
        targets = _test_targets(path, pattern)
        if pattern and not targets:
            return None, framework, f"No files match {pattern} in {path}"

    if framework == "pytest":
        cmd = [_python(path), "-m", "pytest", "-v"] + targets
    elif framework == "unittest":
        # cwd is already path, so discovery starts at "."
        if targets:
            cmd = [_python(path), "-m", "unittest", "-v"] + targets
        else:
            cmd = [_python(path), "-m", "unittest", "discover", "-v", "-s", ".", "-p", "test*.py"]
    elif framework == "jest":
        cmd = ["npx", "jest"] + ([pattern] if pattern else [])
    elif framework == "go":
        cmd = ["go", "test", "-v", pattern or "./..."]
    else:
        return None, framework, f"Unknown framework: {framework}"
    return cmd, framework, ""


def describe_test_run(path: str = None, pattern: str = None, framework: str = "auto") -> str:
    """What test_run(path, pattern, framework) will run, for the user to see before they allow it"""
    path = "." if path is None else path
    try:
        cmd, framework, error = _test_command(path, pattern, framework)
    except Exception as e:  # an argument of the wrong type; test_run itself will report it
        cmd, error = None, f"{type(e).__name__}: {e}"
    if cmd is None:
        return f"Run the tests in {path} (this will fail: {error})"
    return f"Run the tests ({framework}) in {path}:\n  {' '.join(cmd)}"


def _test_run(path: str = None, pattern: str = None, framework: str = "auto") -> dict:
    """Run the tests (internal implementation)

    Args:
        path: Project directory (default: the current directory)
        pattern: Test file, directory or glob to run. Default: every test the framework finds
        framework: test framework (auto/pytest/unittest/jest/go)

    Returns:
        success: whether it passed
        returncode: exit code
        framework: the detected framework
        stdout: standard output
        stderr: standard error
        passed: number passed
        failed: number failed
        errors: number of errors
    """
    if path is None:
        path = "."

    cmd, framework, error = _test_command(path, pattern, framework)
    if cmd is None:
        return {"success": False, "error": error, "framework": framework}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=path,
            timeout=120
        )

        output = result.stdout + result.stderr

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "framework": framework,
            "command": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "passed": _parse_passed(output),
            "failed": _parse_failed(output),
            "errors": _parse_errors(output)
        }
    except FileNotFoundError:
        # The directory exists (checked above), so the program is missing
        return {
            "success": False,
            "error": f"{cmd[0]} was not found. Is {framework} installed?",
            "framework": framework
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "framework": framework
        }


def _default_test_target(source: str) -> str:
    """Where the tests for source go, in a tests/ folder at the project root (the current directory):

        src/calculator.py      -> tests/test_calculator.py
        src/pkg/util.py        -> tests/pkg/test_util.py
        service/src/api.py     -> service/tests/test_api.py
        app/models.py          -> tests/app/test_models.py
        calculator.py          -> tests/test_calculator.py

    The tests for a file outside the current directory go to tests/ at the project root too:
    write_file refuses paths outside the project, so a tests/ folder next to that file could not
    be written anyway.
    """
    name = os.path.splitext(os.path.basename(source))[0]
    rel = os.path.relpath(source)
    if rel.startswith(os.pardir):  # outside the project
        return os.path.join("tests", f"test_{name}.py")

    folders = list(os.path.normpath(os.path.dirname(rel)).split(os.sep))
    folders = [f for f in folders if f not in ("", os.curdir)]
    if "src" in folders:
        i = folders.index("src")
        folders = folders[:i] + ["tests"] + folders[i + 1:]
    else:
        folders = ["tests"] + folders
    return os.path.join(*folders, f"test_{name}.py")


def _test_generate(source: str, target: str = None, framework: str = "pytest") -> dict:
    """Read a source file so the model can write tests for it (internal implementation)

    Args:
        source: Source file path
        target: Test file path (default: see _default_test_target, e.g. src/calculator.py ->
            tests/test_calculator.py)
        framework: Test framework (default pytest)

    Returns:
        success, source, source_content (for the model to write tests from), target, framework,
        suggested_imports, framework_hint and message
    """
    if not os.path.exists(source):
        return {
            "success": False,
            "error": f"Source file not found: {source}",
            "source": source,
            "source_content": None,
            "target": target,
            "framework": framework,
            "suggested_imports": []
        }

    try:
        with open(source, "r", encoding="utf-8") as f:
            source_content = f.read()
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read source: {e}",
            "source": source,
            "source_content": None,
            "target": target,
            "framework": framework,
            "suggested_imports": []
        }

    if target is None:
        # Before (kept for comparison): "/src/" was replaced only with slashes on both sides, which a
        # relative path like "src" never has, and "tests" was then added inside the source folder,
        # so src/calculator.py got src/tests/test_calculator.py
        target = _default_test_target(source)
        # The tests folder is not created here: test_generate runs without asking, and it used to
        # create folders anywhere, even outside the project. write_file creates it when the tests
        # are written, after the user approves, and only inside the project.

    suggested_imports = _extract_imports(source_content)

    name_without_ext = os.path.splitext(os.path.basename(source))[0]

    if framework == "pytest":
        fixture_hint = f'''
# Suggested pytest fixture:
@pytest.fixture
def {name_without_ext}_instance():
    from {name_without_ext} import ...
    return ...
'''
    elif framework == "unittest":
        fixture_hint = '''
# Suggested unittest setUp:
def setUp(self):
    from ... import ...
    self.instance = ...
'''
    else:
        fixture_hint = ""

    imports_section = "\n".join(suggested_imports) if suggested_imports else "# (no imports found)"

    framework_hint = f"""
## {framework.upper()} tests

### Source file: {source}
### Test file to write: {target}

### Imports in the source:
{imports_section}

{fixture_hint}

### Task:
Write complete tests for the source above. The tests should:
1. Cover the main behavior
2. Include edge cases
3. Check expected results with clear asserts
4. Run as they are
"""

    return {
        "success": True,
        "source": source,
        "source_content": source_content,
        "target": target,
        "framework": framework,
        "suggested_imports": suggested_imports,
        "framework_hint": framework_hint,
        "message": f"Source analyzed. Target: {target}. Generate tests based on the source content above."
    }


def _extract_imports(source_content: str) -> list:
    """Extract the import lines from source code"""
    imports = []
    for line in source_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
    return imports[:10]  # at most 10


# Public API - wrapper functions for external use
def test_run(path: str = None, pattern: str = None, framework: str = "auto") -> dict:
    """执行测试

    Args:
        path: Project directory (default: the current directory)
        pattern: Test file, directory or glob to run, e.g. tests/test_calc.py.
            Default: every test the framework finds
        framework: 测试框架 (auto/pytest/unittest/jest/go)

    Returns:
        success: whether it passed
        returncode: exit code
        framework: the detected framework
        stdout: standard output
        stderr: standard error
        passed: number passed
        failed: number failed
        errors: number of errors
    """
    return _test_run(path=path, pattern=pattern, framework=framework)


def test_generate(source: str, target: str = None, framework: str = "pytest") -> dict:
    """Read a source file to prepare writing tests for it

    Returns the source so the LLM can write test cases.
    The LLM writes the test code, which is then saved with write_file.

    Args:
        source: source file path
        target: test file path (worked out from source by default)
        framework: test framework (pytest by default)

    Returns:
        success: whether it worked
        source: source file path
        source_content: the source code (for the LLM to write tests from)
        target: test file path
        framework: the framework used
        suggested_imports: suggested import lines
        framework_hint: framework-specific hints
        message: a message
    """
    return _test_generate(source=source, target=target, framework=framework)
