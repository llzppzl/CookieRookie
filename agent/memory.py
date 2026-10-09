"""agent/memory.py"""
import os
import json
from datetime import datetime
from typing import Optional


class ProjectMemory:
    """Remembers a project's layout and commands in .agent-memory.json in the project folder"""

    DEFAULT_STRUCTURE = {
        "src_dir": None,
        "test_dir": None,
        "main_file": None,
        "test_pattern": "test_*.py"
    }

    DEFAULT_TOOLS = {
        "test_command": "",
        "run_command": "",
        "build_command": "",
        "install_command": ""
    }

    def __init__(self, project_path: str):
        """Load the memory file, or start a new memory if there is none"""
        self.project_path = project_path
        self.path = os.path.join(project_path, ".agent-memory.json")
        self.data = self._load()

    def _load(self) -> dict:
        """Load .agent-memory.json, or return the default memory if it is missing or unreadable"""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._create_default()

    def _create_default(self) -> dict:
        """The memory of a project nothing is known about yet"""
        return {
            "project_path": self.project_path,
            "updated_at": datetime.now().isoformat(),
            "structure": self.DEFAULT_STRUCTURE.copy(),
            "tools": self.DEFAULT_TOOLS.copy(),
            "notes": []
        }

    def save(self) -> None:
        """Write the memory to .agent-memory.json"""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def update_structure(self, info: dict) -> None:
        """Update the project layout (src_dir, test_dir, ...) and save"""
        self.data["structure"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def update_tools(self, info: dict) -> None:
        """Update the project commands (test_command, ...) and save"""
        self.data["tools"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def get_context(self) -> str:
        """The memory as text for the model"""
        lines = ["## Project memory"]

        s = self.data.get("structure", {})
        if any(s.values()):
            lines.append("### Project structure")
            for k, v in s.items():
                if v:
                    lines.append(f"- {k}: {v}")

        t = self.data.get("tools", {})
        if any(t.values()):
            lines.append("### Commands")
            for k, v in t.items():
                if v:
                    lines.append(f"- {k}: {v}")

        lines.append(f"\nLast updated: {self.data.get('updated_at', 'unknown')}")

        return "\n".join(lines)

    def is_stale(self, days: int = 7) -> bool:
        """Whether the memory is older than the given number of days"""
        updated = self.data.get("updated_at")
        if not updated:
            return True
        try:
            updated_dt = datetime.fromisoformat(updated)
            delta = datetime.now() - updated_dt
            return delta.days > days
        except (ValueError, TypeError):
            return True
