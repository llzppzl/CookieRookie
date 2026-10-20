# CookieRookie Project Memory System Design

**Date**: 2026-04-07
**Version**: 1.0
**Status**: Approved

---

## 1. Goal

Add a project memory system to the CookieRookie Coding Agent so the Agent can remember the project structure and tool configuration, and load this context automatically on every run, without having to learn the project again each time.

---

## 2. Design Decisions

| Dimension | Choice | Rationale |
|------|------|------|
| Information scope | Project structure + tool configuration | Balances amount of information and usefulness |
| Storage | JSON file (`.agent-memory.json`) | Human-readable, hand-editable, can be tracked in git |
| Integration | Automatically injected into the Agent context | Seamless and transparent to the user |
| Auto-exploration | Yes, detect project structure on initialization | Works out of the box |

---

## 3. Architecture

```
┌─────────────────────────────────────────┐
│           ProjectMemory                 │
│  - Project structure (dirs, files)      │
│  - Tool config (test cmd, run cmd)      │
│  - Last updated time                    │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────┐      ┌─────────────┐
│ .agent-     │      │ Agent       │
│ memory.json │      │ Context     │
│ (per proj.) │ ───► │ (injected)  │
└─────────────┘      └─────────────┘
```

---

## 4. Memory File Format

**File location**: `{project_path}/.agent-memory.json`

```json
{
  "project_path": "/path/to/project",
  "updated_at": "2026-04-07T10:00:00",
  "structure": {
    "src_dir": "src",
    "test_dir": "tests",
    "main_file": "src/main.py",
    "test_pattern": "test_*.py"
  },
  "tools": {
    "test_command": "python -m pytest",
    "run_command": "python main.py",
    "build_command": "",
    "install_command": "pip install -r requirements.txt"
  },
  "notes": []
}
```

---

## 5. ProjectMemory API

### 5.1 Class Definition

```python
class ProjectMemory:
    """Project memory manager"""

    def __init__(self, project_path: str):
        """Initialize; load or create the memory file"""
        self.path = os.path.join(project_path, ".agent-memory.json")
        self.data = self._load()

    def _load(self) -> dict:
        """Load .agent-memory.json; create a default one if it does not exist"""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._create_default()

    def save(self) -> None:
        """Persist to file"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def update_structure(self, info: dict) -> None:
        """Update the project structure"""
        self.data["structure"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def update_tools(self, info: dict) -> None:
        """Update the tool configuration"""
        self.data["tools"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def get_context(self) -> str:
        """Get the string to inject into the Agent"""
        lines = ["## Project Memory"]

        # Project structure
        s = self.data.get("structure", {})
        if any(s.values()):
            lines.append("### Project Structure")
            for k, v in s.items():
                if v:
                    lines.append(f"- {k}: {v}")

        # Tool configuration
        t = self.data.get("tools", {})
        if any(t.values()):
            lines.append("### Common Commands")
            for k, v in t.items():
                if v:
                    lines.append(f"- {k}: {v}")

        lines.append(f"\nLast updated: {self.data.get('updated_at', 'unknown')}")

        return "\n".join(lines)

    def is_stale(self, days: int = 7) -> bool:
        """Check whether the memory is stale (older than the given number of days)"""
        updated = self.data.get("updated_at")
        if not updated:
            return True
        # Compare dates...
        return False
```

---

## 6. Auto-Detecting Project Structure

```python
def auto_detect_structure(project_path: str) -> dict:
    """Automatically detect the project structure"""

    structure = {
        "src_dir": None,
        "test_dir": None,
        "main_file": None,
        "test_pattern": "test_*.py"
    }

    # Detect the source directory
    for name in ["src", "lib", "app", "source"]:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["src_dir"] = name
            break

    # Detect the test directory
    for name in ["tests", "test", "spec", "__tests__"]:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["test_dir"] = name
            break

    # Detect the main entry file
    for name in ["main.py", "index.js", "main.js", "app.py"]:
        if os.path.isfile(os.path.join(project_path, name)):
            structure["main_file"] = name
            break

    return structure
```

---

## 7. InteractiveAgent Integration

```python
class InteractiveAgent:
    def __init__(self, llm_client, tool_system, project_path: str = None):
        self.llm = llm_client
        self.tool_system = tool_system
        self.project_path = project_path
        self.max_iterations = max_iterations
        self.pending_action = None

        # Initialize memory
        if project_path:
            self.memory = ProjectMemory(project_path)
            # Auto-explore and update memory
            structure = auto_detect_structure(project_path)
            self.memory.update_structure(structure)
        else:
            self.memory = None

    def _build_initial_context(self, task: str) -> dict:
        context = {
            "task": task,
            "history": [],
            "system": self._build_system_prompt()
        }

        # Automatically inject memory
        if self.memory:
            memory_context = self.memory.get_context()
            context["memory"] = memory_context

        return context
```

---

## 8. New/Modified Files

### New

| File | Responsibility |
|------|------|
| `agent/memory.py` | ProjectMemory class |
| `agent/explorer.py` | auto_detect_structure() |

### Modified

| File | Change |
|------|------|
| `agent/core.py` | Integrate the memory system into InteractiveAgent |

---

## 9. Usage

### 9.1 Automatic Memory

```python
# Detected and saved automatically when the Agent is initialized
agent = InteractiveAgent(llm_client, tool_system, project_path="/path/to/project")
# .agent-memory.json is created automatically
```

### 9.2 Memory File

```json
{
  "project_path": "/path/to/project",
  "updated_at": "2026-04-07T10:00:00",
  "structure": {
    "src_dir": "src",
    "test_dir": "tests",
    "main_file": "main.py",
    "test_pattern": "test_*.py"
  },
  "tools": {
    "test_command": "python -m pytest",
    "run_command": "python main.py",
    "build_command": "",
    "install_command": "pip install -r requirements.txt"
  },
  "notes": []
}
```

### 9.3 Injected Result

On every Agent run, the context will include:

```
## Project Memory

### Project Structure
- src_dir: src
- test_dir: tests
- main_file: main.py
- test_pattern: test_*.py

### Common Commands
- test_command: python -m pytest
- run_command: python main.py

Last updated: 2026-04-07T10:00:00
```

---

## 10. Implementation Order

1. `agent/memory.py` - ProjectMemory class
2. `agent/explorer.py` - auto_detect_structure()
3. Modify `agent/core.py` - integrate the memory system
4. Testing
