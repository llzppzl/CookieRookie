"""
Test Tools - run and generate tests
"""

import os
import re
import subprocess
from typing import Dict, Optional

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
    import glob
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


def _test_run(path: str = None, pattern: str = "test_*.py", framework: str = "auto") -> dict:
    """执行测试 (内部实现)

    Args:
        path: 测试路径 (默认当前目录)
        pattern: 测试文件匹配模式
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
    if path is None:
        path = "."

    # 自动检测框架
    if framework == "auto":
        framework = _detect_framework(path)

    try:
        if framework == "pytest":
            cmd = ["python", "-m", "pytest", pattern, "-v"]
        elif framework == "unittest":
            cmd = ["python", "-m", "unittest", "discover", "-s", path, "-p", pattern]
        elif framework == "jest":
            cmd = ["npx", "jest", pattern]
        elif framework == "go":
            cmd = ["go", "test", "./...", "-v"]
        else:
            return {
                "success": False,
                "error": f"Unknown framework: {framework}",
                "framework": framework
            }

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
            "stdout": result.stdout,
            "stderr": result.stderr,
            "passed": _parse_passed(output),
            "failed": _parse_failed(output),
            "errors": _parse_errors(output)
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"File not found: {path}",
            "framework": framework
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "framework": framework
        }


def _test_generate(source: str, target: str = None, framework: str = "pytest") -> dict:
    """分析源码并准备生成测试 (内部实现)

    读取源码内容，返回给 LLM 生成测试用例。

    Args:
        source: 源代码文件路径
        target: 目标测试文件路径 (默认推导: src/calculator.py -> tests/test_calculator.py)
        framework: 测试框架 (默认 pytest)

    Returns:
        success: 是否成功
        source: 源代码路径
        source_content: 源码内容 (供 LLM 生成测试用)
        target: 目标测试路径
        framework: 使用的框架
        suggested_imports: 建议的 import 语句
        message: 提示信息
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

    # 读取源码内容
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

    # 推导 target 路径
    if target is None:
        basename = os.path.basename(source)
        name_without_ext = os.path.splitext(basename)[0]
        dirname = os.path.dirname(source)

        # 构建 tests 目录路径
        if dirname:
            tests_dir = os.path.join(
                dirname.replace("/src/", "/tests/").replace("\\src\\", "\\tests\\"),
                "tests"
            )
        else:
            tests_dir = "tests"

        os.makedirs(tests_dir, exist_ok=True)
        target = os.path.join(tests_dir, f"test_{name_without_ext}.py")

    # 分析源码，提取建议的 import
    suggested_imports = _extract_imports(source_content)

    # 生成框架提示
    basename = os.path.basename(source)
    name_without_ext = os.path.splitext(basename)[0]

    if framework == "pytest":
        fixture_hint = f'''
# pytest 建议 fixture:
@pytest.fixture
def {name_without_ext}_instance():
    from {name_without_ext} import ...
    return ...
'''
    elif framework == "unittest":
        fixture_hint = '''
# unittest 建议 setUp:
def setUp(self):
    from ... import ...
    self.instance = ...
'''
    else:
        fixture_hint = ""

    imports_section = "\n".join(suggested_imports) if suggested_imports else "# (no imports found)"

    framework_hint = f"""
## {framework.upper()} 测试框架

### 源码文件: {source}
### 要生成的测试文件: {target}

### 源码中的 import:
{imports_section}

{fixture_hint}

### 任务:
请根据上面的源码内容，生成完整的测试用例。
测试应该:
1. 覆盖主要功能
2. 包含边界条件测试
3. 使用 assert 明确验证预期结果
4. 生成可运行的测试代码
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
def test_run(path: str = None, pattern: str = "test_*.py", framework: str = "auto") -> dict:
    """执行测试

    Args:
        path: 测试路径 (默认当前目录)
        pattern: 测试文件匹配模式
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
