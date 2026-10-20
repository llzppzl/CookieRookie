# CookieRookie Task Planning Enhancement Design

**Date**: 2026-04-07
**Version**: 1.0
**Status**: Approved

---

## 1. Goal

Add multi-step task planning to CookieRookie so the Agent can:
- Understand complex tasks and break them down into multiple steps
- Show the full execution plan for the user to review
- Support skipping and modifying plan steps
- Execute non-confirmation steps automatically, reducing tedious interaction

---

## 2. Design Decisions

| Dimension | Choice | Rationale |
|------|------|------|
| Plan granularity | Fine-grained (goal steps) | Transparent plan; the user can intervene early |
| Execution mode | Step by step (pause only on confirmable) | Balances safety and efficiency |
| Display format | Numbered list + confirmable marker | Clear, easy to read, easy to reference |

---

## 3. Overall Flow

```
User enters a task
    │
    ▼
┌─────────────────────────┐
│  LLM planning           │
│  Generate Plan          │
└────┬────────────────────┘
     │
     ▼
┌─────────────────────────┐
│  Show Plan              │
│  Await user approval    │
└────┬────────────────────┘
     │
     ▼
┌─────────────────────────┐
│  Execute Plan           │
│  confirmable → pause    │
│  non-confirmable → auto │
└────┬────────────────────┘
     │
     ▼
  Report results
```

---

## 4. Plan Structure

### 4.1 PlanStep

```python
PlanStep = {
    "step": int,           # Step number
    "tool": str,          # Tool name
    "args": dict,         # Tool arguments
    "description": str,     # Step description
    "confirmable": bool    # Whether confirmation is required
}
```

### 4.2 Plan

```python
Plan = {
    "steps": List[PlanStep],  # List of steps
    "summary": str            # Task summary
}
```

---

## 5. Plan Display Format

```
## Execution Plan

1. [read_file] Read src/calculator.py to understand the current implementation
2. [write_file] Create the test file tests/test_calculator.py
3. [edit_file] Implement the add() function
4. [edit_file] Implement the subtract() function ✅ needs confirmation
5. [test_run] Run tests to verify

Confirm execution? (/confirm /reject /skip N)
```

---

## 6. New InteractiveAgent Methods

### 6.1 plan()

```python
def plan(self, task: str) -> Plan:
    """Have the LLM generate an execution plan for the task

    Returns:
        Plan object containing the list of steps and a summary
    """
```

### 6.2 execute_plan()

```python
def execute_plan(self, plan: Plan) -> str:
    """Execute the Plan

    - Non-confirmable steps run automatically
    - Confirmable steps pause and wait for confirmation
    - Returns the execution result
    """
```

### 6.3 _format_plan()

```python
def _format_plan(self, plan: Plan) -> str:
    """Format the Plan as readable text

    Returns:
        Formatted plan text
    """
```

---

## 7. SYSTEM_PROMPT Changes

Add "planning mode" guidance:

```
## Planning Mode

When the user enters a complex task, plan first, then execute:

1. Analyze the steps the task requires
2. Use plan(task) to generate an execution plan
3. Show the plan to the user for confirmation
4. After the user confirms, use execute_plan(plan) to execute it

## Output Format

When planning, return:
```
plan: true
summary: task summary
steps:
  1. [tool] description
  2. [tool] description
  ...
```

When executing, return:
```
thought: your reasoning
action: tool_name(args)
done: true/false
summary: summary
```
```

---

## 8. New main.py Commands

| Command | Description |
|------|------|
| `/plan` | View the execution plan for the current task |
| `/skip N` | Skip step N |
| `/confirm` | Confirm execution (already exists) |
| `/reject` | Reject the plan (already exists) |

---

## 9. New/Modified Files

### Modified

| File | Change |
|------|------|
| `agent/core.py` | Add plan(), execute_plan(), _format_plan() methods; update SYSTEM_PROMPT |
| `main.py` | Add /plan, /skip commands |

---

## 10. Implementation Order

1. Modify the InteractiveAgent SYSTEM_PROMPT to add planning mode
2. Implement the plan() method
3. Implement the execute_plan() method
4. Implement the _format_plan() method
5. Modify main.py to add /plan, /skip commands
6. Testing

---

## 11. Usage Example

```bash
python main.py --interactive
> Write tests for the calculator module and implement the features

## Execution Plan

1. [read_file] Read src/calculator.py
2. [write_file] Create tests/test_calculator.py
3. [edit_file] Implement the add() function ✅ needs confirmation
4. [edit_file] Implement the subtract() function ✅ needs confirmation
5. [test_run] Run tests

> /confirm  # Confirm execution

# The Agent runs steps 1 and 2 automatically, then pauses for confirmation of step 3
```
