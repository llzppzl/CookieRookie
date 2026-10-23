"""agent/test_history_actions.py - past actions in the history are calls the reply format accepts

Models copy the way the history writes their past actions. Before, string arguments were put
between double quotes as they were, so new_string='print("hi")' showed as
new_string="print("hi")", and a command with a line break was split over two lines.
"""
import main


def action_line(tool, args):
    context = {"task": "task", "history": [{
        "action": {"tool": tool, "args": args},
        "result": {"success": True}, "thought": "t", "iteration": 1}]}
    text = main.LLMClient("key")._build_user_message(context)
    return next(line for line in text.splitlines() if line.startswith(" Action: "))[len(" Action: "):]


def parses_back(tool, args):
    assert main.LLMClient("key")._parse_action(action_line(tool, args)) == (tool, args)


def test_quotes_inside_a_value_are_escaped():
    line = action_line("edit_file", {"path": "app.py", "line": 3, "new_string": 'print("hi")'})
    assert line == 'edit_file(path="app.py", line=3, new_string="print(\\"hi\\")")'
    parses_back("edit_file", {"path": "app.py", "line": 3, "new_string": 'print("hi")'})


def test_a_command_with_quotes_and_line_breaks_stays_on_one_line():
    command = 'python -c "import sys\nprint(sys.argv)" \'a b\''
    assert "\n" not in action_line("exec", {"command": command})
    parses_back("exec", {"command": command})


def test_numbers_booleans_and_text_keep_their_form():
    assert action_line("search_files", {"pattern": "def (", "use_regex": False, "path": "."}) == \
        'search_files(pattern="def (", use_regex=False, path=".")'
    parses_back("git_log", {"limit": 5})


def test_non_ascii_text_is_shown_as_it_is():
    assert action_line("search_files", {"pattern": "café"}) == 'search_files(pattern="café")'


def test_a_long_new_string_is_still_left_out():
    line = action_line("edit_file", {"path": "a.py", "line": 1, "new_string": "x" * 60})
    assert line == 'edit_file(path="a.py", line=1, new_string="[cut off]")'
