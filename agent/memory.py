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
        self._keep_out_of_git()

    def _keep_out_of_git(self) -> None:
        """List the memory file in the project's .git/info/exclude. It holds this machine's full path
        to the project, and `git add .` (which git_commit runs without files) would otherwise commit
        it to the user's repository. The exclude file is local: it is never committed or pushed."""
        git_dir = os.path.join(self.project_path, ".git")
        if not os.path.isdir(git_dir):
            return
        name = os.path.basename(self.path)
        exclude = os.path.join(git_dir, "info", "exclude")
        try:
            existing = ""
            if os.path.exists(exclude):
                with open(exclude, "r", encoding="utf-8") as f:
                    existing = f.read()
            if name in (line.strip().lstrip("/") for line in existing.splitlines()):
                return
            os.makedirs(os.path.dirname(exclude), exist_ok=True)
            with open(exclude, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"/{name}\n")
        except OSError:
            pass  # memory still works; the file just shows up in git status

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
