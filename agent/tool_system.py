"""
ToolSystem - 插件化工具注册表
"""

from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    fn: Callable
    confirmable: bool = False
    description: str = ""
    args_schema: Optional[Dict[str, Any]] = None


class ToolSystem:
    """工具注册与管理"""

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        confirmable: bool = False,
        description: str = "",
        args_schema: Optional[Dict[str, Any]] = None
    ) -> None:
        """注册工具"""
        self._tools[name] = ToolDef(
            name=name,
            fn=fn,
            confirmable=confirmable,
            description=description,
            args_schema=args_schema
        )

    def get(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDef]:
        """列出所有工具"""
        return self._tools.copy()

    def is_confirmable(self, name: str) -> bool:
        """检查工具是否需要确认"""
        tool = self._tools.get(name)
        return tool.confirmable if tool else False


# 全局实例
tool_system = ToolSystem()