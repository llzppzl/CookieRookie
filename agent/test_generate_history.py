"""agent/test_generate_history.py - the model sees the whole source test_generate read

test_generate returns the source file for the model to write tests from. Its result used to go
through the 800-character JSON view of other tools, so for any file of more than a few dozen
lines the model saw the start of the source and never the test file path or the hint.
"""
import main
from agent.history import compact_history
from agent import test_tools

# Not imported by name: pytest would collect it as a test
prepare = test_tools._test_generate


def history_text(result, source):
    context = {"task": "task", "history": [{
        "action": {"tool": "test_generate", "args": {"source": source}},
        "result": result, "thought": "t", "iteration": 1}]}
    return main.LLMClient("key")._build_user_message(compact_history(context))


def write_source(tmp_path, lines):
    source = tmp_path / "calculator.py"
    source.write_text("".join(f"def f{i}(x):\n    return x + {i}\n" for i in range(lines)), encoding="utf-8")
    return str(source)


def test_the_whole_source_the_target_and_the_hint_are_shown(tmp_path):
    source = write_source(tmp_path, 60)  # about 1.5 KB of JSON, cut off at 800 before
    result = prepare(source)
    text = history_text(result, source)
    assert "return x + 59" in text
    assert f"Write them to {result['target']} (pytest)" in text
    assert "Write complete tests for the source above" in text
    assert "Result(raw)" not in text


def test_the_source_has_line_numbers():
    text = history_text({"success": True, "source": "a.py", "source_content": "x = 1\ny = 2\n",
                         "target": "tests/test_a.py", "framework": "pytest"}, "a.py")
    assert "   1 | x = 1" in text
    assert "   2 | y = 2" in text


def test_a_very_long_source_says_where_to_read_the_rest(tmp_path):
    source = write_source(tmp_path, 2000)
    text = history_text(prepare(source), source)
    assert f"read the rest of {source} with read_file" in text
    assert len(text) < main.MAX_SOURCE_CHARS + 2000


def test_an_older_step_without_its_source_still_names_the_target(tmp_path):
    source = write_source(tmp_path, 5)
    step = {"action": {"tool": "test_generate", "args": {"source": source}},
            "result": prepare(source), "thought": "t", "iteration": 1}
    other = {"action": {"tool": "read_file", "args": {"path": source}},
             "result": {"success": True, "content": "x", "lines": "1-1", "total": 1}, "thought": "t", "iteration": 2}
    context = {"task": "task", "history": [step] + [other] * 9}
    text = main.LLMClient("key")._build_user_message(compact_history(context))
    assert "Write them to tests" in text
    assert "return x + 4" not in text
