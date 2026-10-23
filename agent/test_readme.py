"""agent/test_readme.py - the README's project structure lists files that exist"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tree_paths():
    """The paths in the README's "Project Structure" tree, built from the indentation"""
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    block = re.search(r"## Project Structure\s+```\n(.*?)```", readme, re.DOTALL).group(1)
    paths, parents = [], []
    for line in block.splitlines()[1:]:  # the first line is the CookieRookie/ folder itself
        match = re.match(r"^((?:│   |    )*)[├└]── (\S+)", line)
        if not match:
            continue
        depth = len(match.group(1)) // 4
        name = match.group(2)
        parents = parents[:depth] + [name.rstrip("/")]
        paths.append("/".join(parents))
    return paths


def test_the_tree_is_read():
    paths = tree_paths()
    assert "agent/core.py" in paths
    assert "main.py" in paths


def test_every_path_in_the_tree_exists():
    missing = [p for p in tree_paths() if "*" not in p and not os.path.exists(os.path.join(ROOT, p))]
    assert missing == []
