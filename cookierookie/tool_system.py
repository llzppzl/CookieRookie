"""
ToolSystem - 插件化工具注册表
"""

import inspect
import typing
from typing import Dict, Callable, Any, List, Optional
from dataclasses import dataclass


JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def schema_from_signature(fn: Callable) -> Dict[str, Any]:
    """Build a JSON Schema for a tool's arguments from its signature, for tools registered
    without args_schema. Parameters without a default are required."""
    properties, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = param.annotation
        if typing.get_origin(annotation) is typing.Union:  # Optional[str]
            options = [a for a in typing.get_args(annotation) if a is not type(None)]
            annotation = options[0] if len(options) == 1 else None
        annotation = typing.get_origin(annotation) or annotation  # List[str] -> list
        properties[name] = {"type": JSON_TYPES.get(annotation, "string")}
        if param.default is param.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


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

    def api_tools(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """The tools (all, or only names) as tool definitions for the Anthropic Messages API"""
        specs = []
        for tool in self._tools.values():
            if names is not None and tool.name not in names:
                continue
            description = tool.description or (inspect.getdoc(tool.fn) or tool.name).splitlines()[0]
            specs.append({
                "name": tool.name,
                "description": description,
                "input_schema": tool.args_schema or schema_from_signature(tool.fn),
            })
        return specs


# 全局实例
tool_system = ToolSystem()