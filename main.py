"""
Debug Agent 入口
支持多种 LLM 提供商 (Minimax, DeepSeek, Kimi, GLM, Anthropic)
"""

import os
import sys
import json
import re
import requests

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import DebugAgent
from agent.core import create_interactive_agent


# 获取当前项目目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


class LLMClient:
    """通用 LLM 客户端 (Anthropic 兼容模式)"""
    
    def __init__(self, api_key: str, model: str = "MiniMax-M2.5", base_url: str = "https://api.minimax.io/anthropic"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
    
    def chat(self, context: dict) -> dict:
        """调用 LLM API (Anthropic 兼容格式)"""
        messages = [
            {"role": "user", "content": self._build_user_message(context)}
        ]
        
        # 添加 system prompt
        system_prompt = context.get("system", "")
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
            "system": system_prompt
        }
        
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=data,
            timeout=60
        )
        
        if response.status_code != 200:
            return {"action": None, "error": f"API error: {response.status_code} - {response.text[:500]}", "raw": response.text}
        
        result = response.json()
        
        # 遍历所有 content blocks
        json_content = ""
        thinking_content = ""
        
        if "content" in result:
            for block in result["content"]:
                if block.get("type") == "text":
                    json_content = block.get("text", "")
                elif block.get("type") == "thinking":
                    thinking_content = block.get("thinking", "")
        
        # 打印 thinking（调试用）
        if thinking_content:
            print(f"\n=== LLM Thinking ===\n{thinking_content[:300]}...\n=====================\n")
        
        # 解析响应
        parsed = self._parse_response(json_content)
        
        if parsed:
            parsed["raw"] = json_content
            return parsed
        
        return {"action": None, "error": f"Failed to parse: {json_content[:200]}", "raw": json_content}
    
    def _parse_response(self, content: str) -> dict:
        """解析 LLM 响应 - 支持多种格式"""
        content = content.strip()
        
        result = {
            "thought": "",
            "action": {},
            "done": False,
            "summary": ""
        }
        
        # 提取 thought
        thought_match = re.search(r'thought:\s*(.+?)(?=\naction:|$)', content, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()
        
        # 提取 action
        action_match = re.search(r'action:\s*(.+?)(?=\ndone:|$)', content, re.DOTALL)
        if action_match:
            action_str = action_match.group(1).strip()
            if action_str:
                func_match = re.match(r'(\w+)\((.*)\)', action_str)
                if func_match:
                    tool_name = func_match.group(1)
                    args_str = func_match.group(2)
                    args = self._parse_args(args_str)
                    result["action"] = {"tool": tool_name, "args": args}
        
        # 提取 done
        done_match = re.search(r'done:\s*(true|false)', content, re.IGNORECASE)
        if done_match:
            result["done"] = done_match.group(1).lower() == "true"
        
        # 提取 summary
        summary_match = re.search(r'summary:\s*(.+?)$', content, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()
        
        if not result["thought"] and not result["action"]:
            return None
        
        return result
    
    def _parse_args(self, args_str: str) -> dict:
        """解析工具参数 - 支持多种格式"""
        args = {}
        
        # 数字参数: key=123
        for match in re.finditer(r'(\w+)=(\d+)', args_str):
            args[match.group(1)] = int(match.group(2))
        
        # 双引号字符串: key="value"
        for match in re.finditer(r'(\w+)="((?:[^"\\]|\\.)*)"', args_str):
            key = match.group(1)
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            args[key] = value
        
        # 单引号字符串: key='value'
        for match in re.finditer(r'(\w+)=\'((?:[^\'\\]|\\.)*)\'', args_str):
            key = match.group(1)
            value = match.group(2).replace("\\'", "'").replace('\\\\', '\\')
            args[key] = value
        
        return args
    
    def _build_user_message(self, context: dict) -> str:
        """构建用户消息"""
        parts = []
        
        # Bug 报告
        parts.append(f"## Bug Report\n{context['bug_report']}")
        
        # 历史记录
        if context["history"]:
            parts.append("\n## History (你之前做了什么)")
            for h in context["history"]:
                action = h.get("action", {})
                result = h.get("result", {})
                thought = h.get("thought", "")
                iteration = h.get("iteration", "?")
                
                tool_name = action.get("tool", "unknown")
                args = action.get("args", {})
                
                parts.append(f"\n### 第 {iteration} 轮")
                parts.append(f" Thought: {thought}")
                
                if tool_name and tool_name != "unknown":
                    args_parts = []
                    for k, v in args.items():
                        if k == "new_string" and len(str(v)) > 50:
                            args_parts.append(f'{k}="[内容截断]"')
                        else:
                            args_parts.append(f'{k}="{v}"' if isinstance(v, str) else f'{k}={v}')
                    args_str = ", ".join(args_parts)
                    parts.append(f" Action: {tool_name}({args_str})")
                
                # ===== 旧的结果摘要逻辑（保留作学习对比） =====
                # if tool_name == "read_file" and result.get("success"):
                #     parts.append(f" Result: 文件内容已读取")
                # elif tool_name == "exec" and result.get("success"):
                #     stdout = result.get("stdout", "").strip()
                #     if len(stdout) > 100:
                #         stdout = stdout[:100] + "..."
                #     parts.append(f" Result: {stdout}")
                # elif tool_name == "edit_file" and result.get("success"):
                #     parts.append(f" Result: 文件已修改")
                # elif not result.get("success"):
                #     parts.append(f" Result: 失败 - {result.get('error', result.get('stderr', 'unknown'))}")
                # else:
                #     parts.append(f" Result: success")

                # ===== 新的结果摘要逻辑：保留状态 + 关键细节 =====
                success = result.get("success")

                # 统一的失败分支
                if success is False:
                    error_msg = result.get("error", result.get("stderr", "unknown"))
                    parts.append(f" Result: 失败 - {error_msg}")
                    continue

                # 没有 result 的情况
                if result is None:
                    parts.append(" Result: 无返回结果")
                    continue

                # 按工具类型分别给出「一句话总结 + 关键字段」
                if tool_name == "read_file" and success:
                    lines = result.get("lines", "?")
                    total = result.get("total", "?")
                    content = result.get("content", "")

                    parts.append(f" Result: 读取了 {lines} 行（共 {total} 行）代码。")

                    # 对长文件做截断，但明确标出
                    max_chars = 2000
                    snippet = content
                    truncated = False
                    if len(snippet) > max_chars:
                        snippet = snippet[:max_chars]
                        truncated = True

                    if snippet:
                        parts.append("\n```code\n" + snippet + ("\n... [内容已截断]" if truncated else "") + "\n```")

                elif tool_name == "exec":
                    returncode = result.get("returncode")
                    stdout = (result.get("stdout") or "").strip()
                    stderr = (result.get("stderr") or "").strip()

                    parts.append(f" Result: 命令执行完成，returncode={returncode}.")

                    def _truncate(text: str, label: str) -> str:
                        if not text:
                            return ""
                        max_len = 800
                        if len(text) > max_len:
                            return f"{label}（前 {max_len} 字符）：\n{text[:max_len]}\n... [输出已截断]\n"
                        return f"{label}：\n{text}\n"

                    snippet_blocks = []
                    if stdout:
                        snippet_blocks.append(_truncate(stdout, "STDOUT"))
                    if stderr:
                        snippet_blocks.append(_truncate(stderr, "STDERR"))

                    if snippet_blocks:
                        parts.append("\n" + "\n".join(snippet_blocks))

                elif tool_name == "edit_file" and success:
                    path = result.get("path") or args.get("path", "")
                    line_no = result.get("line") or args.get("line")
                    mode = result.get("mode") or ("line" if "line" in args else "old_string")
                    new_line = result.get("new_line")

                    summary = f" Result: 编辑成功（mode={mode}"
                    if line_no:
                        summary += f", line={line_no}"
                    if path:
                        summary += f", path={path}"
                    summary += ")."
                    parts.append(summary)

                    if new_line:
                        parts.append(f" 新行内容: {new_line}")

                elif tool_name == "search_files" and success:
                    count = result.get("count", 0)
                    matches = result.get("matches") or []
                    parts.append(f" Result: 搜索到 {count} 处匹配。")

                    # 展示前若干条匹配，避免一次性塞太多
                    max_items = 5
                    if matches:
                        parts.append(" 部分匹配示例：")
                        for m in matches[:max_items]:
                            parts.append(f"  - {m.get('file')}:{m.get('line')}: {m.get('content')}")
                        if count > max_items:
                            parts.append(f"  ... 其余 {count - max_items} 条已省略。")

                elif tool_name == "find_files" and success:
                    count = result.get("count", 0)
                    matches = result.get("matches") or []
                    parts.append(f" Result: 找到 {count} 个文件。")

                    max_items = 10
                    if matches:
                        parts.append(" 文件列表（部分）：")
                        for p in matches[:max_items]:
                            parts.append(f"  - {p}")
                        if count > max_items:
                            parts.append(f"  ... 其余 {count - max_items} 个已省略。")

                else:
                    # 其他工具：直接给出一个截断后的 JSON 视图，避免完全丢信息
                    try:
                        result_json = json.dumps(result, ensure_ascii=False)
                        max_len = 800
                        if len(result_json) > max_len:
                            result_json = result_json[:max_len] + "... [结果已截断]"
                        parts.append(f" Result(raw): {result_json}")
                    except Exception:
                        parts.append(f" Result: {result}")

            # 原来的“重要提示”在很多情况下与事实不符，这里注释掉保留作为学习对比
            # parts.append("\n## 重要提示")
            # parts.append("你已经在历史记录中看到了代码内容，请分析它并决定下一步该做什么！")
            # parts.append("不要再次读取文件，除非你需要查看其他文件。")
            # parts.append("绝对不要修改已经修复好的代码！")
        
        return "\n".join(parts)


def load_config():
    """从 .env 文件加载配置"""
    env_path = os.path.join(PROJECT_DIR, ".env")
    
    config = {
        "api_key": None,
        "model": "MiniMax-M2.5",
        "base_url": "https://api.minimax.io/anthropic"
    }
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    config["api_key"] = line.split("=", 1)[1].strip()
                elif line.startswith("ANTHROPIC_BASE_URL="):
                    config["base_url"] = line.split("=", 1)[1].strip()
                elif line.startswith("MODEL_ID="):
                    config["model"] = line.split("=", 1)[1].strip()
    
    return config


def main():
    # 获取 bug 描述
    bug_report = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DEBUG_BUG_REPORT", "")
    
    if not bug_report:
        print("Usage: python main.py \"Your bug description\"")
        print("Or set DEBUG_BUG_REPORT environment variable")
        return
    
    # 加载配置
    config = load_config()
    
    if not config["api_key"]:
        print("Error: ANTHROPIC_API_KEY not found in .env")
        print(f"Please create .env file in {PROJECT_DIR}")
        print("See .env.example for reference")
        return
    
    print(f"Config: model={config['model']}, base_url={config['base_url']}")
    
    # 创建客户端和 agent
    llm_client = LLMClient(
        config["api_key"], 
        config["model"], 
        config["base_url"]
    )
    agent = DebugAgent(llm_client)
    
    # 运行
    print(f"Starting Debug Agent ({config['model']})...")
    print(f"Bug: {bug_report}\n")
    
    result = agent.run(bug_report)
    print(f"\n=== Final Result ===\n{result}")


def interactive_main():
    """交互模式入口"""
    config = load_config()

    if not config["api_key"]:
        print("Error: ANTHROPIC_API_KEY not found in .env")
        return

    print(f"CookieRookie Coding Agent ({config['model']})")
    print("Type 'exit' to quit, 'help' for commands\n")

    # 初始化组件
    from agent.tool_system import tool_system
    from agent import tools as tools_module
    tools_module.register_base_tools()

    from agent.core import create_interactive_agent

    llm_client = LLMClient(
        config["api_key"],
        config["model"],
        config["base_url"]
    )
    agent = create_interactive_agent(llm_client, tool_system)
    agent.current_plan = None

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                break

            if user_input == "/confirm":
                if agent.pending_action:
                    result = agent.confirm()
                    print(f"\n{result}\n")
                else:
                    print("No pending action")
                continue

            if user_input.startswith("/reject"):
                parts = user_input.split(" ", 1)
                instructions = parts[1] if len(parts) > 1 else None
                result = agent.reject(instructions)
                print(f"\n{result}\n")
                continue

            if user_input.startswith("/edit"):
                parts = user_input[5:].strip()
                modifications = {}
                for part in parts.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        modifications[k] = v
                if modifications and agent.pending_action:
                    result = agent.edit_and_confirm(modifications)
                    print(f"\n{result}\n")
                else:
                    print("Invalid /edit usage or no pending action")
                continue

            if user_input == "/status":
                print(f"Pending action: {agent.pending_action is not None}")
                if agent.pending_action:
                    print(f"Tool: {agent.pending_action['action']['tool']}")
                continue

            if user_input == "/plan":
                if hasattr(agent, 'current_plan') and agent.current_plan:
                    formatted = agent._format_plan(agent.current_plan)
                    print(f"\n{formatted}\n")
                else:
                    print("No plan available. Enter a task first.")
                continue

            if user_input.startswith("/skip"):
                parts = user_input.split()
                if len(parts) > 1:
                    try:
                        step_num = int(parts[1])
                        if hasattr(agent, 'skip_step'):
                            result = agent.skip_step(step_num)
                            print(f"\n{result}\n")
                        else:
                            print("Skip not supported")
                    except ValueError:
                        print("Invalid step number")
                continue

            if user_input in ["/help", "/h", "help"]:
                print("""
CookieRookie Coding Agent - 可用命令

任务输入:
  直接输入任务描述，Agent 会自动执行

交互命令:
  /confirm          确认执行当前待确认的操作
  /reject           拒绝当前待确认的操作，让 Agent 重新规划
  /edit key=value   修改待确认操作的参数后执行
  /status           查看当前待确认操作的状态
  /plan             查看当前计划
  /skip <step>      跳过指定步骤

退出:
  exit, quit        退出交互模式

示例:
  > 帮我写一个计算器模块
  > 为 src/calculator.py 生成测试
  > 修复登录功能的 bug
""")
                continue

            # 普通任务
            result = agent.run(user_input)

            if result == "awaiting_confirmation":
                # 等待用户在下一轮确认
                pass
            else:
                print(f"\n{result}\n")

        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_main()
    else:
        main()
