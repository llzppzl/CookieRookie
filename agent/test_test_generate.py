"""agent/test_test_generate.py - where test_generate puts the tests"""
import os

# Imported under another name, or pytest would collect it as a test
from agent.test_tools import test_generate as generate_tests


def make(path, text="x = 1\n"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_tests_go_to_the_tests_folder_at_the_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cases = {
        "src/calculator.py": os.path.join("tests", "test_calculator.py"),
        "src/pkg/util.py": os.path.join("tests", "pkg", "test_util.py"),
        "service/src/api.py": os.path.join("service", "tests", "test_api.py"),
        "app/models.py": os.path.join("tests", "app", "test_models.py"),
        "calculator.py": os.path.join("tests", "test_calculator.py"),
    }
    for source, target in cases.items():
        make(source)
        assert generate_tests(source)["target"] == target, source


def test_no_tests_folder_inside_src(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make("src/calculator.py")
    generate_tests("src/calculator.py")
    assert not (tmp_path / "src" / "tests").exists()


def test_generate_changes_nothing_on_disk(tmp_path, monkeypatch):
    """It runs without asking, so it only reads. write_file creates the folder later."""
    monkeypatch.chdir(tmp_path)
    make("src/calculator.py")
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    generate_tests("src/calculator.py")
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before


def test_a_source_outside_the_project_gets_tests_inside_it(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    make(str(outside / "secret.py"))
    monkeypatch.chdir(project)
    result = generate_tests(os.path.join("..", "outside", "secret.py"))
    assert result["target"] == os.path.join("tests", "test_secret.py")
    assert not (outside / "tests").exists()


def test_write_file_creates_the_tests_folder(tmp_path, monkeypatch):
    from agent.tools import write_file
    monkeypatch.chdir(tmp_path)
    make("src/calculator.py")
    target = generate_tests("src/calculator.py")["target"]
    assert write_file(target, "def test_x():\n    pass\n")["success"] is True
    assert (tmp_path / "tests" / "test_calculator.py").is_file()


def test_an_explicit_target_is_kept(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make("src/calculator.py")
    assert generate_tests("src/calculator.py", target="spec/calc_spec.py")["target"] == "spec/calc_spec.py"


def test_hint_is_in_english(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make("src/calculator.py", "import math\n\ndef area(r):\n    return math.pi * r * r\n")
    result = generate_tests("src/calculator.py")
    assert "Write complete tests" in result["framework_hint"]
    assert not any(0x4E00 <= ord(c) <= 0x9FFF for c in result["framework_hint"])
    assert "import math" in result["suggested_imports"]
