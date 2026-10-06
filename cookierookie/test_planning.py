"""cookierookie/test_planning.py - plans: /plan, /skip, /reject, /confirm (fake LLM, no API calls)"""
import copy

from unittest.mock import MagicMock
from cookierookie import cli
from cookierookie.core import InteractiveAgent
from cookierookie.tool_system import tool_system
import cookierookie.tools as tools_module


class TestPlanning:
    @classmethod
    def setup_class(cls):
        """注册基础工具"""
        tools_module.register_base_tools()

    def test_format_plan(self):
        """测试 Plan 格式化"""
        agent = InteractiveAgent(MagicMock(), tool_system)

        plan = {
            "summary": "测试任务",
            "steps": [
                {"step": 1, "tool": "read_file", "description": "读取文件", "confirmable": False},
                {"step": 2, "tool": "edit_file", "description": "编辑文件", "confirmable": True},
                {"step": 3, "tool": "exec", "description": "运行", "confirmable": True, "skipped": True},
            ]
        }

        formatted = agent._format_plan(plan)
        assert formatted.startswith("Plan: 测试任务")
        assert "1. [read_file] 读取文件\n" in formatted
        assert "2. [edit_file] 编辑文件  (asks you first)" in formatted
        assert "3. [exec] 运行  (skipped)" in formatted
        assert "/confirm" in formatted and "/skip N" in formatted

    def test_parse_plan_response(self):
        """测试解析 Plan 响应"""
        agent = InteractiveAgent(MagicMock(), tool_system)

        response = """
plan: true
summary: 测试任务
steps:
  1. [read_file] 读取文件
  2. [write_file] 创建文件
"""
        plan = agent._parse_plan_response(response)
        assert plan["summary"] == "测试任务"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["tool"] == "read_file"
        assert plan["steps"][0]["confirmable"] is False
        assert plan["steps"][1]["tool"] == "write_file"
        assert plan["steps"][1]["confirmable"] is True  # write_file is confirmable

    def test_plan_method_exists(self):
        """测试 plan 方法存在"""
        agent = InteractiveAgent(MagicMock(), tool_system)
        assert hasattr(agent, 'plan')


class ScriptedLLM:
    """Gives the replies in order, and keeps a copy of each context it was sent"""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(copy.deepcopy(context))
        return self.replies.pop(0)


def plan_reply(*steps, summary="Add divide() to calc.py and test it"):
    lines = "\n".join(f"  {n}. {step}" for n, step in enumerate(steps, 1))
    return {"raw": f"plan: true\nsummary: {summary}\nsteps:\n{lines}", "done": False}


DIVIDE_PLAN = plan_reply("[read_file] Read calc.py",
                         "[edit_file] Add divide(), raising ZeroDivisionError for 0",
                         "[test_run] Run the tests")


def done(summary):
    return {"thought": "", "action": {}, "done": True, "summary": summary}


def agent_with(*replies):
    return InteractiveAgent(ScriptedLLM(*replies), tool_system)


def test_a_plan_is_shown_and_nothing_runs():
    agent = agent_with(DIVIDE_PLAN)

    shown = agent.propose_plan("add a divide function to calc.py")

    assert "Plan: Add divide() to calc.py and test it" in shown
    assert "1. [read_file] Read calc.py\n" in shown
    assert "2. [edit_file] Add divide(), raising ZeroDivisionError for 0  (asks you first)" in shown
    assert len(agent.llm.contexts) == 1
    assert "tools" not in agent.llm.contexts[0]
    assert agent.pending_action is None
    assert agent.show_plan() == shown


def test_skip_leaves_a_step_out():
    agent = agent_with(DIVIDE_PLAN)
    agent.propose_plan("add a divide function to calc.py")

    assert "3. [test_run] Run the tests  (skipped)" in agent.skip_step(3)
    assert agent.skip_step(4) == "The plan has no step 4. Its steps are 1 to 3."
    assert agent.skip_step(0) == "The plan has no step 0. Its steps are 1 to 3."


def test_confirm_runs_the_plan_without_the_skipped_steps():
    agent = agent_with(DIVIDE_PLAN, done("Added divide()."))
    agent.propose_plan("add a divide function to calc.py")
    agent.skip_step(3)

    assert agent.confirm() == "Added divide()."

    task = agent.llm.contexts[1]["task"]
    assert task.startswith("add a divide function to calc.py")
    assert "The user approved this plan" in task
    assert "1. [read_file] Read calc.py\n" in task
    assert "3. [test_run] Run the tests (the user skipped this step: don't do it)" in task
    assert agent.llm.contexts[1]["tools"]
    assert agent.current_plan is None
    assert agent.confirm() == "Nothing to confirm."


def test_edits_in_a_plan_still_wait_for_the_user(tmp_path):
    target = tmp_path / "calc.py"
    agent = agent_with(
        plan_reply(f"[write_file] Create {target}"),
        {"thought": "create it", "action": {"tool": "write_file",
                                            "args": {"path": str(target), "content": "x = 1\n"}}, "done": False},
        done("Created calc.py."),
    )
    agent.propose_plan("create calc.py")

    assert agent.confirm() == "awaiting_confirmation"
    assert not target.exists()

    assert agent.confirm() == "Created calc.py."
    assert target.read_text() == "x = 1\n"


def test_a_pending_action_is_answered_before_the_plan(tmp_path):
    target = tmp_path / "notes.txt"
    agent = agent_with(
        {"thought": "", "action": {"tool": "write_file", "args": {"path": str(target), "content": "hi"}}, "done": False},
        DIVIDE_PLAN,
        done("Wrote notes.txt."),
    )
    assert agent.run("write notes.txt") == "awaiting_confirmation"
    agent.propose_plan("add a divide function to calc.py")

    assert agent.confirm() == "Wrote notes.txt."
    assert target.read_text() == "hi"
    assert agent.current_plan is not None


def test_every_step_skipped_runs_nothing():
    agent = agent_with(plan_reply("[read_file] Read calc.py"))
    agent.propose_plan("look at calc.py")
    agent.skip_step(1)

    assert agent.confirm() == "Every step of the plan is skipped, so nothing ran."
    assert len(agent.llm.contexts) == 1


def test_reject_without_a_reason_drops_the_plan():
    agent = agent_with(DIVIDE_PLAN)
    agent.propose_plan("add a divide function to calc.py")

    assert agent.reject() == "Plan dropped; nothing ran."
    assert agent.current_plan is None
    assert agent.show_plan() == "No plan. Make one with /plan <task>."
    assert agent.reject() == "Nothing to reject."


def test_reject_with_a_reason_changes_the_plan():
    agent = agent_with(DIVIDE_PLAN, plan_reply("[read_file] Read calc.py",
                                               "[edit_file] Add divide() for ints and floats"))
    agent.propose_plan("add a divide function to calc.py")

    shown = agent.reject("also handle floats, and don't run the tests")

    request = agent.llm.contexts[1]["task"]
    assert "add a divide function to calc.py" in request
    assert "Your last plan was:\n1. [read_file] Read calc.py" in request
    assert "3. [test_run] Run the tests" in request
    assert "The user wants it changed: also handle floats, and don't run the tests" in request
    assert "2. [edit_file] Add divide() for ints and floats" in shown
    assert agent.current_plan["task"] == "add a divide function to calc.py"
    assert len(agent.current_plan["steps"]) == 2


def test_a_reply_without_steps_keeps_the_plan():
    agent = agent_with(DIVIDE_PLAN, {"raw": "Which file is calc.py in?", "done": False})
    agent.propose_plan("add a divide function to calc.py")

    shown = agent.reject("use the other calc.py")

    assert "no new plan" in shown
    assert "The plan from before is still waiting" in shown
    assert "Which file is calc.py in?" in shown
    assert len(agent.current_plan["steps"]) == 3


def test_an_api_error_makes_no_plan():
    agent = agent_with({"fatal": True, "error": "401 Unauthorized: invalid x-api-key", "done": False})

    assert agent.propose_plan("add a divide function") == "LLM error: 401 Unauthorized: invalid x-api-key"
    assert agent.current_plan is None


def test_plan_steps_with_markdown_are_read():
    agent = InteractiveAgent(MagicMock(), tool_system)

    plan = agent._parse_plan_response(
        "**plan:** true\n"
        "**summary:** Add divide()\n"
        "**steps:**\n"
        "1. **[read_file]** Read calc.py\n"
        "3) [`edit_file`] Add divide()\n"
        "- 4. [ test_run ] Run the tests\n")

    assert plan["summary"] == "Add divide()"
    assert [(step["step"], step["tool"]) for step in plan["steps"]] == \
        [(1, "read_file"), (2, "edit_file"), (3, "test_run")]
    assert plan["steps"][1]["confirmable"] is True


def test_plan_commands_in_the_terminal(monkeypatch, capsys):
    llm = ScriptedLLM(DIVIDE_PLAN, done("Added divide()."))
    monkeypatch.setattr(cli, "load_config", lambda: {"api_key": "key", "model": "m", "base_url": "u",
                                                     "max_tokens": 100})
    monkeypatch.setattr("cookierookie.core.create_interactive_agent",
                        lambda client, tools: InteractiveAgent(llm, tools))
    typed = iter(["/plan add a divide function to calc.py", "/skip x", "/skip 3", "/plan", "/confirm", "/status",
                  "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(typed))

    cli.interactive_main()

    out = capsys.readouterr().out
    assert "2. [edit_file] Add divide(), raising ZeroDivisionError for 0  (asks you first)" in out
    assert "Usage: /skip N" in out
    assert out.count("3. [test_run] Run the tests  (skipped)") == 2
    assert "Added divide()." in out
    assert "Nothing is waiting." in out
    assert llm.contexts[0]["task"].endswith("add a divide function to calc.py")