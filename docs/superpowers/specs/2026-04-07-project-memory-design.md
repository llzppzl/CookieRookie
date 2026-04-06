# CookieRookie 项目记忆系统设计

**日期**: 2026-04-07
**版本**: 1.0
**状态**: 已批准

---

## 1. 目标

为 CookieRookie Coding Agent 添加项目记忆系统，使 Agent 能够记住项目结构、工具配置，在每次运行时自动加载上下文，无需重复了解项目。

---

## 2. 设计决策

| 维度 | 选择 | 理由 |
|------|------|------|
| 信息范围 | 项目结构 + 工具配置 | 平衡信息量和实用性 |
| 存储方式 | JSON 文件 (`.agent-memory.json`) | 人类可读、可手动编辑、可 git 管理 |
| 集成方式 | 自动注入到 Agent context | 无缝衔接，对用户透明 |
| 自动探索 | 是，初始化时检测项目结构 | 开箱即用 |

---

## 3. 架构

```
┌─────────────────────────────────────────┐
│           ProjectMemory                  │
│  - 项目结构 (目录、文件)                 │
│  - 工具配置 (测试命令、启动命令)         │
│  - 最后更新时间                          │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────┐      ┌─────────────┐
│ .agent-     │      │ Agent       │
│ memory.json │      │ Context     │
│ (每个项目)  │ ───► │ (自动注入)   │
└─────────────┘      └─────────────┘
```

---

## 4. 记忆文件格式

**文件位置**: `{project_path}/.agent-memory.json`

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

### 5.1 类定义

```python
class ProjectMemory:
    """项目记忆管理器"""

    def __init__(self, project_path: str):
        """初始化，加载或创建记忆文件"""
        self.path = os.path.join(project_path, ".agent-memory.json")
        self.data = self._load()

    def _load(self) -> dict:
        """加载 .agent-memory.json，不存在则创建默认"""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._create_default()

    def save(self) -> None:
        """持久化到文件"""
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

        # 项目结构
        s = self.data.get("structure", {})
        if any(s.values()):
            lines.append("### 项目结构")
            for k, v in s.items():
                if v:
                    lines.append(f"- {k}: {v}")

        # 工具配置
        t = self.data.get("tools", {})
        if any(t.values()):
            lines.append("### 常用命令")
            for k, v in t.items():
                if v:
                    lines.append(f"- {k}: {v}")

        lines.append(f"\n最后更新: {self.data.get('updated_at', '未知')}")

        return "\n".join(lines)

    def is_stale(self, days: int = 7) -> bool:
        """检查记忆是否过期（超过指定天数）"""
        updated = self.data.get("updated_at")
        if not updated:
            return True
        # 比较日期...
        return False
```

---

## 6. 自动探索项目结构

```python
def auto_detect_structure(project_path: str) -> dict:
    """自动检测项目结构"""

    structure = {
        "src_dir": None,
        "test_dir": None,
        "main_file": None,
        "test_pattern": "test_*.py"
    }

    # 检测源码目录
    for name in ["src", "lib", "app", "source"]:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["src_dir"] = name
            break

    # 检测测试目录
    for name in ["tests", "test", "spec", "__tests__"]:
        if os.path.isdir(os.path.join(project_path, name)):
            structure["test_dir"] = name
            break

    # 检测主入口文件
    for name in ["main.py", "index.js", "main.js", "app.py"]:
        if os.path.isfile(os.path.join(project_path, name)):
            structure["main_file"] = name
            break

    return structure
```

---

## 7. InteractiveAgent 集成

```python
class InteractiveAgent:
    def __init__(self, llm_client, tool_system, project_path: str = None):
        self.llm = llm_client
        self.tool_system = tool_system
        self.project_path = project_path
        self.max_iterations = max_iterations
        self.pending_action = None

        # 初始化记忆
        if project_path:
            self.memory = ProjectMemory(project_path)
            # 自动探索并更新记忆
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

        # 自动注入记忆
        if self.memory:
            memory_context = self.memory.get_context()
            context["memory"] = memory_context

        return context
```

---

## 8. 新增/修改文件

### 新增

| 文件 | 职责 |
|------|------|
| `agent/memory.py` | ProjectMemory 类 |
| `agent/explorer.py` | auto_detect_structure() |

### 修改

| 文件 | 改动 |
|------|------|
| `agent/core.py` | InteractiveAgent 集成记忆系统 |

---

## 9. 使用方式

### 9.1 自动记忆

```python
# Agent 初始化时自动检测并保存
agent = InteractiveAgent(llm_client, tool_system, project_path="/path/to/project")
# .agent-memory.json 自动创建
```

### 9.2 记忆文件

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

### 9.3 注入效果

Agent 每次运行时，context 中会包含：

```
## 项目记忆

### 项目结构
- src_dir: src
- test_dir: tests
- main_file: main.py
- test_pattern: test_*.py

### 常用命令
- test_command: python -m pytest
- run_command: python main.py

最后更新: 2026-04-07T10:00:00
```

---

## 10. 实现顺序

1. `agent/memory.py` - ProjectMemory 类
2. `agent/explorer.py` - auto_detect_structure()
3. 修改 `agent/core.py` - 集成记忆系统
4. 测试
