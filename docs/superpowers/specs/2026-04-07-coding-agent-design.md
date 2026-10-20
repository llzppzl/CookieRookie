# CookieRookie Coding Agent Design

**Date**: 2026-04-07
**Version**: 1.0
**Status**: Draft

---

## 1. Goal

Turn CookieRookie from a debug agent into a general coding agent, with features on par with Claude Code.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────┐
│              User (CLI)                  │
│         /confirm /reject /edit            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│           InteractiveAgent               │
│  - run_task(task) → autonomous loop     │
│  - ask_confirmation(action) → wait      │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         ToolSystem (plugins)             │
│  - register(name, tool_fn, confirmable) │
│  - Base: read_file, edit_file, exec     │
│  - Built in: git_*, test_*              │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         LLMClient (multi-provider)       │
└─────────────────────────────────────────┘
```

---

## 3. InteractiveAgent main loop

```
User enters a task
    │
    ▼
┌─────────────────┐
│  Parse the task │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  Build a plan   │
│  (LLM steps)    │
└────┬────────────┘
     │
     ▼
┌─────────────────┐     ┌──────────────┐
│  Run the plan   │────►│ Needs okay?  │
│  (each step)    │     └──────┬───────┘
└────┬────────────┘            │
     │              ┌─────────▼─────────┐
     │              │  Wait for user     │
     │              │  /confirm          │
     │              │  /reject           │
     │              │  /edit <changes>   │
     │              └─────────┬─────────┘
     │                        │
     │◄────────────────────────┘
     ▼
┌─────────────────┐
│  Check result   │
└────┬────────────┘
     │
     ▼
  Report the result
```

---

## 4. Tool system design

### 4.1 Tool definition

```python
ToolDef = {
    "name": str,           # tool name
    "fn": Callable,        # function that does the work
    "confirmable": bool,   # whether the user must confirm it
    "description": str,    # tool description
    "args_schema": dict    # argument schema
}
```

### 4.2 Registration

```python
tool_system.register(
    name="git_commit",
    fn=git_commit,
    confirmable=True,
    description="Commit changes to git",
    args_schema={"message": str, "files": list}
)
```

### 4.3 Built-in tools

| Category | Tools | confirmable |
|----------|-------|-------------|
| File | read_file, edit_file, write_file | edit_file=True, write_file=True |
| Execute | exec, run_test | exec=True |
| Git | git_status, git_diff, git_commit, git_branch | all True |
| Test | test_run, test_generate | test_run=True |

---

## 5. Confirm / reject protocol

```
The agent proposes an action that needs confirmation
    │
    ▼
┌─────────────────────────────────────┐
│  Shown to the user:                  │
│                                     │
│  Thought: I'll change main.py l.20  │
│  Action: edit_file(path="main.py",  │
│           line=20,                  │
│           new_string='...')          │
│                                     │
│  Waiting for the user:               │
│  /confirm  - run it                 │
│  /reject   - refuse, LLM replans    │
│  /edit ...   - change args, then run │
└─────────────────────────────────────┘
```

---

## 6. Test framework design

### 6.1 TestRunner

```python
class TestRunner:
    def detect_framework(self, path) -> str
        # detect pytest / unittest / jest / go test, ...

    def run(self, path=None, pattern="test_*.py") -> TestResult:
        # returns: passed, failed, errors, output

    def generate(self, source_file, target_file=None) -> str:
        # the LLM writes test cases into the target file
```

### 6.2 Built-in test tools

```python
test_run(path=None, pattern="test_*.py")  # run the tests
test_generate(source="src/calculator.py",
               target="tests/test_calculator.py")  # generate tests
```

### 6.3 TDD flow

```
task → write code → write tests → run tests → fail → fix code → run tests → pass
```

---

## 7. Code generation

### 7.1 Scope

- **New files**: create new modules or files from a description
- **Edit existing files**: change, extend, refactor
- **Full refactors**: understand the code structure, then change it systematically

### 7.2 Tools

```python
write_file(path, content)       # create or overwrite a file
edit_file(path, line, ...)      # edit an existing file
create_module(name, template)  # create a module skeleton
```

---

## 8. File layout

```
CookieRookie/
├── agent/
│   ├── __init__.py
│   ├── core.py              # DebugAgent → InteractiveAgent
│   ├── tools.py             # tool registry (refactored)
│   ├── tool_system.py       # new: plugin tool system
│   ├── git_tools.py         # new: git tools
│   └── test_tools.py        # new: test tools
├── docs/
│   └── specs/               # design docs
├── main.py                  # entry point (stays compatible)
└── requirements.txt
```

---

## 9. Implementation order

### Short term (Phase 1)
1. Refactor tool_system.py: plugin tool registration
2. Add the InteractiveAgent class
3. Implement /confirm /reject /edit

### Medium term (Phase 2)
4. Add test_tools.py: run and generate tests
5. Add git_tools.py: git tools
6. Implement TaskAgent (autonomous mode)

### Long term (Phase 3)
7. Improve code generation
8. Add the project memory system
9. Improve the LLM's planning

---

## 10. Compatibility

The `python main.py` entry point stays compatible; the existing debug agent keeps working.
