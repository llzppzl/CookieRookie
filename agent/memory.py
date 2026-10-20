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
        # Set once a save failed, so the note about it is printed only once
        self._save_failed = False

    def _load(self) -> dict:
        """Load .agent-memory.json, or return the default memory if it is missing or unreadable"""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Valid JSON that is not a memory (a list, a string) would break every update
                if isinstance(data, dict) and isinstance(data.get("structure"), dict) \
                        and isinstance(data.get("tools"), dict):
                    return data
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
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

    def save(self) -> bool:
        """Write the memory to .agent-memory.json. Returns False if the project folder can't be
        written to (read-only, owned by someone else): the memory then lasts for this session only,
        instead of the PermissionError stopping interactive mode before it starts."""
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            if not self._save_failed:
                print(f"Note: could not save the project memory to {self.path} "
                      f"({e.strerror or e}); it is kept for this session only.")
            self._save_failed = True
            return False
        self._keep_out_of_git()
        return True

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
        self._update("structure", info)

    def update_tools(self, info: dict) -> None:
        """Update the project commands (test_command, ...) and save"""
        self._update("tools", info)

    def _update(self, section: str, info: dict) -> None:
        """Merge info into a section and save, but only if that changes something (or there is no
        file yet). Interactive mode updates the layout on every start, which used to rewrite the
        file each time and set "Last updated" to now, even when nothing in the project had changed."""
        current = self.data[section]
        if os.path.exists(self.path) and all(k in current and current[k] == v for k, v in info.items()):
            return
        current.update(info)
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
