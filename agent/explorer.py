"""agent/explorer.py"""
import os
from typing import Dict


def auto_detect_structure(project_path: str) -> Dict[str, str]:
    """Detect the project layout from the folders and files that exist

    Args:
        project_path: the project root folder

    Returns:
        The detected layout (src_dir, test_dir, main_file, test_pattern)
    """
    structure = {
        "src_dir": None,
        "test_dir": None,
        "main_file": None,
        "test_pattern": "test_*.py"
    }

    # Source folder, in order of preference
    src_candidates = ["src", "lib", "app", "source"]
    for name in src_candidates:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["src_dir"] = name
            break

    # Test folder, in order of preference
    test_candidates = ["tests", "test", "spec", "__tests__"]
    for name in test_candidates:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["test_dir"] = name
            break

    # Entry point file, in order of preference
    main_candidates = ["main.py", "index.js", "main.js", "app.py", "app/main.py"]
    for name in main_candidates:
        if os.path.isfile(os.path.join(project_path, name)):
            structure["main_file"] = name
            break

    return structure
