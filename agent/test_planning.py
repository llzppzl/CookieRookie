"""agent/test_planning.py - plan mode: /plan, /skip, /confirm and /reject"""
import pytest
from unittest.mock import MagicMock
from agent.core import InteractiveAgent
from agent.tool_system import tool_system
import agent.tools as tools_module


PLAN_REPLY = """
plan: true
summary: Add a test for the calculator
steps:
  1. [read_file] Read src/calculator.py
  2. [write_file] Create tests/test_calculator.py
  3. [test_run] Run the tests
"""


class ScriptedLLM:
    """Returns scripted replies in order and records the context of each call"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.contexts = []

    def chat(self, context):
        self.contexts.append(context)
        return self.replies.pop(0)


def planned_agent(*more_replies):
    llm = ScriptedLLM([{"raw": PLAN_REPLY, "action": None}, *more_replies])
    agent = InteractiveAgent(llm, tool_system)
    agent.propose_plan("add a calculator test")
    return agent, llm


class TestPlanning:
    @classmethod
    def setup_class(cls):
        """Register the base tools"""
        tools_module.register_base_tools()

    def test_format_plan(self):
        agent = InteractiveAgent(MagicMock(), tool_system)

        plan = {
            "summary": "Test task",
            "steps": [
                {"step": 1, "tool": "read_file", "description": "Read the file", "confirmable": False},
                {"step": 2, "tool": "edit_file", "description": "Edit the file", "confirmable": True},
                {"step": 3, "tool": "exec", "description": "Run it", "confirmable": True, "skipped": True},
            ]
        }

        formatted = agent._format_plan(plan)
        assert "Plan: Test task" in formatted
        assert "1. [read_file] Read the file" in formatted
        assert "2. [edit_file] Edit the file  (asks you first)" in formatted
        assert "3. [exec] Run it  (skipped)" in formatted
        assert "/confirm" in formatted

    def test_parse_plan_response(self):
        agent = InteractiveAgent(MagicMock(), tool_system)
        plan = agent._parse_plan_response(PLAN_REPLY)
        assert plan["summary"] == "Add a test for the calculator"
        assert [s["tool"] for s in plan["steps"]] == ["read_file", "write_file", "test_run"]
        assert plan["steps"][0]["confirmable"] is False
        assert plan["steps"][1]["confirmable"] is True  # write_file is confirmable

    def test_markdown_steps_are_read_and_numbered_in_order(self):
        agent = InteractiveAgent(MagicMock(), tool_system)
        plan = agent._parse_plan_response(
            "**summary:** Fix it\n**steps:**\n1. **[read_file]** Read app.py\n3) [`exec`] Run it\n- 7. [test_run] Test\n")
        assert plan["summary"] == "Fix it"
        assert [(s["step"], s["tool"]) for s in plan["steps"]] == [(1, "read_file"), (2, "exec"), (3, "test_run")]

    def test_plan_makes_the_current_plan_and_runs_nothing(self):
        agent, llm = planned_agent()
        assert agent.current_plan["task"] == "add a calculator test"
        assert len(agent.current_plan["steps"]) == 3
        assert "add a calculator test" in llm.contexts[0]["task"]
        assert agent.pending_action is None

    def test_reply_without_steps_makes_no_plan(self):
        agent = InteractiveAgent(ScriptedLLM([{"raw": "I would read the file first.", "action": None}]), tool_system)
        result = agent.propose_plan("do something")
        assert "no steps" in result
        assert agent.current_plan is None

    def test_api_error_is_shown(self):
        llm = ScriptedLLM([{"raw": "", "action": None, "error": "API error: 401 - invalid key"}])
        agent = InteractiveAgent(llm, tool_system)
        assert agent.propose_plan("do something") == "LLM error: API error: 401 - invalid key"

    def test_skip_step(self):
        agent, _ = planned_agent()
        shown = agent.skip_step(2)
        assert "2. [write_file] Create tests/test_calculator.py  (skipped)" in shown
        assert agent.current_plan["steps"][1]["skipped"] is True
        assert "no step 9" in agent.skip_step(9)

    def test_skip_without_a_plan(self):
        agent = InteractiveAgent(MagicMock(), tool_system)
        assert agent.skip_step(1) == InteractiveAgent.NO_PLAN

    def test_execute_plan_runs_it_as_one_task(self):
        done = {"thought": "done", "done": True, "summary": "finished", "action": {}}
        agent, llm = planned_agent(done)
        agent.skip_step(3)

        assert agent.execute_plan() == "finished"
        task = llm.contexts[-1]["task"]
        assert task.startswith("add a calculator test")
        assert "1. [read_file] Read src/calculator.py" in task
        assert "3. [test_run] Run the tests (the user skipped this step: don't do it)" in task
        assert agent.current_plan is None

    def test_plan_with_every_step_skipped_does_not_run(self):
        agent, llm = planned_agent()
        for n in (1, 2, 3):
            agent.skip_step(n)
        assert "nothing ran" in agent.execute_plan()
        assert len(llm.contexts) == 1

    def test_feedback_changes_the_plan(self):
        new_plan = {"raw": "summary: Smaller\nsteps:\n1. [read_file] Read src/calculator.py\n", "action": None}
        agent, llm = planned_agent(new_plan)
        agent.propose_plan(agent.current_plan["task"], "don't write any files")

        request = llm.contexts[-1]["task"]
        assert "Your last plan was" in request
        assert "don't write any files" in request
        assert agent.current_plan["summary"] == "Smaller"

    def test_drop_plan(self):
        agent, _ = planned_agent()
        assert "dropped" in agent.drop_plan()
        assert agent.current_plan is None
