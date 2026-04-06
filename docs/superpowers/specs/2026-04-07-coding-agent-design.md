# CookieRookie Coding Agent 设计文档

**日期**: 2026-04-07
**版本**: 1.0
**状态**: 草稿

---

## 1. 目标

将 CookieRookie 从 Debug Agent 打造成通用 Coding Agent，功能对标 Claude Code。

---

## 2. 架构概览

```
┌─────────────────────────────────────────┐
│              User (CLI)                  │
│         /confirm /reject /edit            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│           InteractiveAgent               │
│  - run_task(task) → 自主执行循环          │
│  - ask_confirmation(action) → 等待用户   │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         ToolSystem (插件化)              │
│  - register(name, tool_fn, confirmable) │
│  - 预置: read_file, edit_file, exec     │
│  - 内置: git_*, test_*                  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         LLMClient (多 provider)          │
└─────────────────────────────────────────┘
```

---

## 3. InteractiveAgent 核心循环

```
用户输入任务
    │
    ▼
┌─────────────────┐
│  解析任务类型    │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  构建 Plan       │
│  (LLM 规划步骤)  │
└────┬────────────┘
     │
     ▼
┌─────────────────┐     ┌──────────────┐
│  执行 Plan      │────►│  需要确认?   │
│  (遍历步骤)     │     └──────┬───────┘
└────┬────────────┘            │
     │              ┌─────────▼─────────┐
     │              │  等待用户确认      │
     │              │  /confirm          │
     │              │  /reject           │
     │              │  /edit <修改>      │
     │              └─────────┬─────────┘
     │                        │
     │◄────────────────────────┘
     ▼
┌─────────────────┐
│  验证结果        │
└────┬────────────┘
     │
     ▼
  报告结果
```

---

## 4. 工具系统设计

### 4.1 工具定义

```python
ToolDef = {
    "name": str,           # 工具名称
    "fn": Callable,        # 实际执行函数
    "confirmable": bool,   # 是否需要用户确认
    "description": str,    # 工具描述
    "args_schema": dict    # 参数 schema
}
```

### 4.2 注册接口

```python
tool_system.register(
    name="git_commit",
    fn=git_commit,
    confirmable=True,
    description="提交更改到 git",
    args_schema={"message": str, "files": list}
)
```

### 4.3 预置工具

| 类别 | 工具 | confirmable |
|------|------|-------------|
| 文件 | read_file, edit_file, write_file | edit_file=True, write_file=True |
| 执行 | exec, run_test | exec=True |
| Git | git_status, git_diff, git_commit, git_branch | 全部 True |
| 测试 | test_run, test_generate | test_run=True |

---

## 5. 确认/拒绝交互协议

```
Agent 发出需要确认的 action
    │
    ▼
┌─────────────────────────────────────┐
│  展示给用户：                        │
│                                     │
│  Thought: 我要修改 main.py 第 20 行  │
│  Action: edit_file(path="main.py",  │
│           line=20,                  │
│           new_string='...')          │
│                                     │
│  等待用户:                           │
│  /confirm  - 确认执行               │
│  /reject   - 拒绝，LLM 重新规划     │
│  /edit ...   - 修改参数后执行        │
└─────────────────────────────────────┘
```

---

## 6. 测试框架设计

### 6.1 TestRunner

```python
class TestRunner:
    def detect_framework(self, path) -> str
        # 检测 pytest / unittest / jest / go test 等

    def run(self, path=None, pattern="test_*.py") -> TestResult:
        # 返回: passed, failed, errors, output

    def generate(self, source_file, target_file=None) -> str:
        # LLM 生成测试用例，写入目标文件
```

### 6.2 内置测试工具

```python
test_run(path=None, pattern="test_*.py")  # 执行测试
test_generate(source="src/calculator.py",
               target="tests/test_calculator.py")  # 生成测试
```

### 6.3 TDD 流程

```
任务 → 生成代码 → 生成测试 → 跑测试 → 失败 → 修复代码 → 跑测试 → 通过
```

---

## 7. 代码生成能力

### 7.1 能力范围

- **生成新文件**: 根据描述创建新模块/文件
- **编辑现有文件**: 修改、扩展、重构
- **完整重构**: 理解代码结构后进行系统性修改

### 7.2 工具

```python
write_file(path, content)       # 创建/覆盖文件
edit_file(path, line, ...)      # 编辑现有文件
create_module(name, template)  # 创建模块骨架
```

---

## 8. 文件结构

```
CookieRookie/
├── agent/
│   ├── __init__.py
│   ├── core.py              # DebugAgent → InteractiveAgent
│   ├── tools.py             # 工具注册表（重构）
│   ├── tool_system.py       # 新增：插件化工具系统
│   ├── git_tools.py         # 新增：Git 工具集
│   └── test_tools.py        # 新增：测试工具集
├── docs/
│   └── specs/               # 设计文档
├── main.py                  # 入口（保持兼容）
└── requirements.txt
```

---

## 9. 实现顺序

### 短期（Phase 1）
1. 重构 tool_system.py - 插件化工具注册
2. 添加 InteractiveAgent 类
3. 实现 /confirm /reject /edit 交互

### 中期（Phase 2）
4. 添加 test_tools.py - 测试执行和生成
5. 添加 git_tools.py - Git 操作工具
6. 实现 TaskAgent（自主执行模式）

### 长期（Phase 3）
7. 完善代码生成能力
8. 添加项目记忆系统
9. 优化 LLM 规划能力

---

## 10. 兼容性

保持 `python main.py` 入口兼容，现有 Debug Agent 功能继续可用。
