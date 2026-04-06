"""agent/explorer.py"""
import os
from typing import Dict


def auto_detect_structure(project_path: str) -> Dict[str, str]:
    """自动检测项目结构

    Args:
        project_path: 项目根目录

    Returns:
        包含检测到的项目结构信息的字典
    """
    structure = {
        "src_dir": None,
        "test_dir": None,
        "main_file": None,
        "test_pattern": "test_*.py"
    }

    # 源码目录检测顺序（优先级）
    src_candidates = ["src", "lib", "app", "source"]
    for name in src_candidates:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["src_dir"] = name
            break

    # 测试目录检测顺序
    test_candidates = ["tests", "test", "spec", "__tests__"]
    for name in test_candidates:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["test_dir"] = name
            break

    # 主入口文件检测顺序
    main_candidates = ["main.py", "index.js", "main.js", "app.py", "app/main.py"]
    for name in main_candidates:
        if os.path.isfile(os.path.join(project_path, name)):
            structure["main_file"] = name
            break

    return structure
