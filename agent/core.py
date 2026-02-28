"""
Debug Agent 核心逻辑
"""

import json
import re
from typing import Optional
from .tools import register_tools


SYSTEM_PROMPT = """你是一个 Debug Agent。你的任务是通过工具自动定位并修复代码中的 bug。

## 工作流程
1. 分析用户提供的 bug 报告
2. 使用工具读取代码，分析错误
3. 修复代码
4. 运行验证
5. 重复直到 bug 修复

## 可用工具
- read_file(path, offset=1, limit=100): 读取文件
- edit_file(path, line=行号, new_string='新内容'): 按行号修改（推荐）
- edit_file(path, old_string="旧内容", new_string="新内容"): 字符串替换（容易出错）
- exec(command, workdir=None, timeout=30): 执行命令
- search_files(pattern, path=".", file_glob="*.py"): 搜索关键词
- find_files(pattern, path="."): 查找文件

## 输出格式（必须严格遵守！）

严格按照这个格式输出，**不要有任何其他内容**：

```
thought: 你的推理过程（1-2句话）
action: 工具名(参数1="值1", 参数2="值2")
done: true/false
summary: 修复总结（仅当done=true时）
```

### 重要：优先使用行号模式！

当需要修改代码时，**优先使用行号模式**，避免字符串匹配问题：

```
# 推荐（按行号修改）
action: edit_file(path="user_manager.py", line=19, new_string='    return user["city"]')

# 注意：如果 new_string 内部包含双引号，请用单引号包裹整个字符串！
action: edit_file(path="file.py", line=10, new_string='print("hello")')
```

### 示例
```
thought: 需要先读取文件查看代码内容
action: read_file(path="examples/calculator.py")
done: false

thought: 发现bug在第15行，需要修改
action: edit_file(path="examples/calculator.py", line=15, new_string='    rate = 0.1')
done: false

thought: 已修复，需要验证运行结果
action: exec(command="python examples/calculator.py")
done: false
```

## 重要规则
1. action 后面必须紧跟括号和参数
2. **修改代码时尽量用 line 模式**，不要用 old_string
3. **new_string 如果包含双引号，请用单引号包裹！**
4. 如果 done=true，action 那一行可以为空
5. 绝对不要重复已经做过的操作！"""


class DebugAgent:
    def __init__(self, llm_client, max_iterations: int = 10):
        self.llm = llm_client
        self.tools = register_tools()
        self.max_iterations = max_iterations
    
    def run(self, bug_report: str) -> str:
        """运行 agent"""
        context = self._build_initial_context(bug_report)
        
        for i in range(self.max_iterations):
            print(f"\n=== Iteration {i + 1} ===")
            
            # 1. LLM 推理
            response = self.llm.chat(context)
            
            # 调试：打印原始响应
            print(f"Raw response:\n{response.get('raw', 'N/A')[:500]}")
            
            # 2. 解析 action
            action = response.get("action")
            reasoning = response.get("thought", "")
            done = response.get("done", False)
            summary = response.get("summary", "")
            
            print(f"Thought: {reasoning}")
            
            if done:
                return summary or "Bug fixed!"
            
            if not action:
                print(f"Warning: No action in response, ending.")
                return f"LLM did not provide action. Response: {response}"
            
            # 3. 执行 action
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            
            if not tool_name:
                return f"Invalid action format: {action}"
            
            if tool_name not in self.tools:
                return f"Unknown tool: {tool_name}"
            
            print(f"Executing: {tool_name}({tool_args})")
            
            tool_func = self.tools[tool_name]
            result = tool_func(**tool_args)
            
            # 打印结果摘要
            result_summary = json.dumps(result, ensure_ascii=False)
            if len(result_summary) > 300:
                result_summary = result_summary[:300] + "..."
            print(f"Result: {result_summary}")
            
            # 4. 更新 context
            context["history"].append({
                "action": action,
                "result": result,
                "thought": reasoning,
                "iteration": i + 1
            })
        
        return "Max iterations reached"
    
    def _build_initial_context(self, bug_report: str) -> dict:
        """构建初始上下文"""
        return {
            "bug_report": bug_report,
            "history": [],
            "system": SYSTEM_PROMPT
        }


def create_agent(llm_client, max_iterations: int = 10) -> DebugAgent:
    """创建 Debug Agent"""
    return DebugAgent(llm_client, max_iterations)
