"""agent/test_action_parsing.py - reading tool calls out of the model's text replies"""
from main import LLMClient


def action_of(action_line):
    reply = f"thought: do it\naction: {action_line}\ndone: false"
    return LLMClient("key")._parse_response(reply)["action"]


def test_escaped_newlines_become_line_breaks():
    action = action_of('write_file(path="a.py", content="line1\\nline2\\n")')
    assert action == {"tool": "write_file", "args": {"path": "a.py", "content": "line1\nline2\n"}}


def test_key_value_text_inside_a_string_is_not_an_argument():
    action = action_of('exec(command="grep -n timeout=5 app.py")')
    assert action["args"] == {"command": "grep -n timeout=5 app.py"}


def test_booleans_and_numbers():
    action = action_of('find_files(pattern="test_.*", use_regex=True)')
    assert action["args"] == {"pattern": "test_.*", "use_regex": True}
    assert action_of('read_file(path="a.py", offset=-1, limit=20)')["args"]["offset"] == -1


def test_real_line_breaks_inside_a_string():
    action = action_of('write_file(path="a.py", content="def f():\n    return 1\n")')
    assert action["args"]["content"] == "def f():\n    return 1\n"


def test_arguments_on_several_lines():
    action = action_of('edit_file(\n    path="a.py",\n    line=3,\n    new_string=\'print("hi")\',\n)')
    assert action["args"] == {"path": "a.py", "line": 3, "new_string": 'print("hi")'}


def test_quotes_inside_strings():
    assert action_of('edit_file(path="a.py", line=1, new_string=\'x = "y"\')')["args"]["new_string"] == 'x = "y"'
    assert action_of('edit_file(path="a.py", line=1, new_string="x = \\"y\\"")')["args"]["new_string"] == 'x = "y"'


def test_text_python_cannot_read_still_uses_the_old_parser():
    # An unquoted value isn't valid Python; the old parser still picks up what it can
    action = action_of('read_file(path="a.py", limit=10, mode=fast)')
    assert action["tool"] == "read_file"
    assert action["args"] == {"path": "a.py", "limit": 10}
