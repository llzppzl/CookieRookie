# CookieRookie 任务规划增强设计

**日期**: 2026-04-07
**版本**: 1.0
**状态**: 已批准

---

## 1. 目标

为 CookieRookie 添加多步骤任务规划能力，使 Agent 能够：
- 理解复杂任务并分解为多个步骤
- 展示完整执行计划供用户审核
- 支持跳过、修改计划步骤
- 自动执行非确认步骤，减少繁琐交互

---

## 2. 设计决策

| 维度 | 选择 | 理由 |
|------|------|------|
| Plan 粒度 | 细粒度（目标步骤） | 计划透明，用户可提前干预 |
| 执行方式 | 逐步执行（confirmable 才暂停） | 安全 + 效率平衡 |
| 展示格式 | 编号列表 + confirmable 标记 | 清晰易读，便于引用 |

---

## 3. 整体流程

```
用户输入任务
    │
    ▼
┌─────────────────┐
│  LLM 规划       │
│  生成 Plan      │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  展示 Plan      │
│  等待用户确认    │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  执行 Plan       │
│  confirmable → 暂停│
│  非 confirmable → 自动│
└────┬────────────┘
     │
     ▼
  报告结果
```

---

## 4. Plan 结构

### 4.1 PlanStep

```python
PlanStep = {
    "step": int,           # 步骤编号
    "tool": str,          # 工具名
    "args": dict,         # 工具参数
    "description": str,     # 步骤描述
    "confirmable": bool    # 是否需要确认
}
```

### 4.2 Plan

```python
Plan = {
    "steps": List[PlanStep],  # 步骤列表
    "summary": str            # 任务总结
}
```

---

## 5. Plan 展示格式

```
## 执行计划

1. [read_file] 读取 src/calculator.py 了解当前实现
2. [write_file] 创建 tests/test_calculator.py 测试文件
3. [edit_file] 实现 add() 函数
4. [edit_file] 实现 subtract() 函数 ✅ 需要确认
5. [test_run] 运行测试验证

确认执行？ (/confirm /reject /skip N)
```

---

## 6. InteractiveAgent 新增方法

### 6.1 plan()

```python
def plan(self, task: str) -> Plan:
    """让 LLM 生成任务的执行计划

    Returns:
        Plan 对象，包含步骤列表和总结
    """
```

### 6.2 execute_plan()

```python
def execute_plan(self, plan: Plan) -> str:
    """执行 Plan

    - 非 confirmable 步骤自动执行
    - confirmable 步骤暂停等待确认
    - 返回执行结果
    """
```

### 6.3 _format_plan()

```python
def _format_plan(self, plan: Plan) -> str:
    """格式化 Plan 为可读文本

    Returns:
        格式化的计划文本
    """
```

---

## 7. SYSTEM_PROMPT 改动

新增"规划模式"指导：

```
## 规划模式

当用户输入复杂任务时，先规划再执行：

1. 分析任务需要的步骤
2. 使用 plan(task) 生成执行计划
3. 展示计划给用户确认
4. 用户确认后使用 execute_plan(plan) 执行

## 输出格式

规划时返回：
```
plan: true
summary: 任务总结
steps:
  1. [tool] 描述
  2. [tool] 描述
  ...
```

执行时返回：
```
thought: 你的推理过程
action: 工具名(参数)
done: true/false
summary: 总结
```
```

---

## 8. main.py 新增命令

| 命令 | 说明 |
|------|------|
| `/plan` | 查看当前任务的执行计划 |
| `/skip N` | 跳过第 N 步 |
| `/confirm` | 确认执行（已存在） |
| `/reject` | 拒绝计划（已存在） |

---

## 9. 新增/修改文件

### 修改

| 文件 | 改动 |
|------|------|
| `agent/core.py` | 新增 plan(), execute_plan(), _format_plan() 方法，更新 SYSTEM_PROMPT |
| `main.py` | 新增 /plan, /skip 命令 |

---

## 10. 实现顺序

1. 修改 InteractiveAgent SYSTEM_PROMPT 增加规划模式
2. 实现 plan() 方法
3. 实现 execute_plan() 方法
4. 实现 _format_plan() 方法
5. 修改 main.py 增加 /plan, /skip 命令
6. 测试

---

## 11. 使用示例

```bash
python main.py --interactive
> 帮我为计算器模块写测试并实现功能

## 执行计划

1. [read_file] 读取 src/calculator.py
2. [write_file] 创建 tests/test_calculator.py
3. [edit_file] 实现 add() 函数 ✅ 需要确认
4. [edit_file] 实现 subtract() 函数 ✅ 需要确认
5. [test_run] 运行测试

> /confirm  # 确认执行

# Agent 自动执行步骤 1, 2，然后暂停等待确认步骤 3
```
