"""agent/memory.py"""
import os
import json
from datetime import datetime
from typing import Optional


class ProjectMemory:
    """项目记忆管理器"""

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
        """初始化，加载或创建记忆文件"""
        self.project_path = project_path
        self.path = os.path.join(project_path, ".agent-memory.json")
        self.data = self._load()

    def _load(self) -> dict:
        """加载 .agent-memory.json，不存在则创建默认"""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._create_default()

    def _create_default(self) -> dict:
        """创建默认记忆"""
        return {
            "project_path": self.project_path,
            "updated_at": datetime.now().isoformat(),
            "structure": self.DEFAULT_STRUCTURE.copy(),
            "tools": self.DEFAULT_TOOLS.copy(),
            "notes": []
        }

    def save(self) -> None:
        """持久化到文件"""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def update_structure(self, info: dict) -> None:
        """更新项目结构"""
        self.data["structure"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def update_tools(self, info: dict) -> None:
        """更新工具配置"""
        self.data["tools"].update(info)
        self.data["updated_at"] = datetime.now().isoformat()
        self.save()

    def get_context(self) -> str:
        """获取注入 Agent 的字符串"""
        lines = ["## 项目记忆"]

        s = self.data.get("structure", {})
        if any(s.values()):
            lines.append("### 项目结构")
            for k, v in s.items():
                if v:
                    lines.append(f"- {k}: {v}")

        t = self.data.get("tools", {})
        if any(t.values()):
            lines.append("### 常用命令")
            for k, v in t.items():
                if v:
                    lines.append(f"- {k}: {v}")

        lines.append(f"\n最后更新: {self.data.get('updated_at', '未知')}")

        return "\n".join(lines)

    def is_stale(self, days: int = 7) -> bool:
        """检查记忆是否过期"""
        updated = self.data.get("updated_at")
        if not updated:
            return True
        try:
            updated_dt = datetime.fromisoformat(updated)
            delta = datetime.now() - updated_dt
            return delta.days > days
        except (ValueError, TypeError):
            return True
