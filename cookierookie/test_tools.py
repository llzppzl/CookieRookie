"""
Test Tools - 测试执行和生成工具
"""

import os
import re
import subprocess
from typing import Dict, Optional

from .tools import write_file

# Tell pytest not to collect functions in this module as tests
__test__ = False


def _detect_framework(path: str = ".") -> str:
    """检测测试框架

    检查 pytest.ini, pyproject.toml, test_*.py 内容

    Args:
        path: 项目路径

    Returns:
        框架名称: pytest, unittest, jest, go
    """
    # 检查 pytest.ini
    pytest_ini = os.path.join(path, "pytest.ini")
    if os.path.exists(pytest_ini):
        with open(pytest_ini, "r", encoding="utf-8") as f:
            content = f.read()
            if "[pytest]" in content:
                return "pytest"

    # 检查 pyproject.toml
    pyproject = os.path.join(path, "pyproject.toml")
    if os.path.exists(pyproject):
        with open(pyproject, "r", encoding="utf-8") as f:
            content = f.read()
            if "pytest" in content:
                return "pytest"

    # 检查 test_*.py 文件内容
    test_pattern = os.path.join(path, "test_*.py")
    import glob
    for test_file in glob.glob(test_pattern):
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            if "unittest.TestCase" in content or "from unittest import" in content:
                return "unittest"
            if "jest" in content.lower():
                return "jest"

    # 检查 go.mod (go test)
    go_mod = os.path.join(path, "go.mod")
    if os.path.exists(go_mod):
        return "go"

    # 检查 package.json (jest)
    package_json = os.path.join(path, "package.json")
    if os.path.exists(package_json):
        with open(package_json, "r", encoding="utf-8") as f:
            content = f.read()
            if "jest" in content:
                return "jest"

    # 默认返回 pytest
    return "pytest"


def _parse_passed(output: str) -> int:
    """从测试输出中解析通过的测试数量"""
    # pytest: "5 passed"
    match = re.search(r"(\d+)\s+passed", output)
    if match:
        return int(match.group(1))
    return 0


def _parse_failed(output: str) -> int:
    """从测试输出中解析失败的测试数量"""
    # pytest: "2 failed"
    match = re.search(r"(\d+)\s+failed", output)
    if match:
        return int(match.group(1))
    return 0


def _parse_errors(output: str) -> int:
    """从测试输出中解析错误的测试数量"""
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
        success: 是否成功
        returncode: 返回码
        framework: 检测到的框架
        stdout: 标准输出
        stderr: 标准错误
        passed: 通过数量
        failed: 失败数量
        errors: 错误数量
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
    """从源码中提取 import 语句"""
    imports = []
    for line in source_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
    return imports[:10]  # 最多 10 个


# Public API - wrapper functions for external use
def test_run(path: str = None, pattern: str = "test_*.py", framework: str = "auto") -> dict:
    """执行测试

    Args:
        path: 测试路径 (默认当前目录)
        pattern: 测试文件匹配模式
        framework: 测试框架 (auto/pytest/unittest/jest/go)

    Returns:
        success: 是否成功
        returncode: 返回码
        framework: 检测到的框架
        stdout: 标准输出
        stderr: 标准错误
        passed: 通过数量
        failed: 失败数量
        errors: 错误数量
    """
    return _test_run(path=path, pattern=pattern, framework=framework)


def test_generate(source: str, target: str = None, framework: str = "pytest") -> dict:
    """分析源码，准备生成测试

    返回源码内容供 LLM 生成测试用例。
    实际测试代码需要通过 LLM 生成后用 write_file 写入。

    Args:
        source: 源代码文件路径
        target: 目标测试文件路径 (默认推导)
        framework: 测试框架 (默认 pytest)

    Returns:
        success: 是否成功
        source: 源代码路径
        source_content: 源码内容 (供 LLM 生成测试用)
        target: 目标测试路径
        framework: 使用的框架
        suggested_imports: 建议的 import 语句
        framework_hint: 框架特定的提示
        message: 提示信息
    """
    return _test_generate(source=source, target=target, framework=framework)
