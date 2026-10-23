"""agent/test_reply_labels.py - the thought:/action:/done: lines are found however the model writes them"""
import pytest

from main import LLMClient

READ = {"tool": "read_file", "args": {"path": "app.py"}}


def parse(reply):
    return LLMClient("key")._parse_response(reply)


@pytest.mark.parametrize("reply", [
    'Thought: read it\nAction: read_file(path="app.py")\nDone: false',
    '**thought:** read it\n**action:** read_file(path="app.py")\n**done:** false',
    '**Thought**: read it\n**Action**: read_file(path="app.py")\n**Done**: false',
    'thought: read it\naction: `read_file(path="app.py")`\ndone: false',
    '```\nthought: read it\naction: read_file(path="app.py")\n```',
    'Let me look at the file.\n\nthought: read it\naction: read_file(path="app.py")\ndone: false',
])
def test_dressed_up_labels_still_give_the_action(reply):
    parsed = parse(reply)
    assert parsed["thought"] == "read it"
    assert parsed["action"] == READ
    assert parsed["done"] is False


def test_action_mentioned_in_the_thought_is_not_the_action():
    parsed = parse('thought: the next action: read the file\naction: read_file(path="app.py")\ndone: false')
    assert parsed["thought"] == "the next action: read the file"
    assert parsed["action"] == READ


def test_done_with_a_summary_on_several_lines():
    parsed = parse("Thought: fixed\nAction:\nDone: True\nSummary: fixed line 3\nand added a test")
    assert parsed["done"] is True
    assert parsed["action"] == {}
    assert parsed["summary"] == "fixed line 3\nand added a test"


def test_label_like_lines_inside_a_written_file_stay_in_the_file():
    reply = ('thought: write the config\n'
             'action: write_file(path="ci.yml", content="summary: nightly\nthought: none\n")\n'
             'done: false')
    action = parse(reply)["action"]
    assert action["args"]["content"] == "summary: nightly\nthought: none\n"


def test_reply_without_labels_is_not_parsed():
    assert parse("I think the bug is on line 3.") is None
