"""
ToolSystem - 插件化工具注册表
"""

import functools
import inspect
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


def checked(name: str, fn: Callable) -> Callable:
    """Wrap fn so that arguments it does not take come back as an error result the model can
    read and correct, instead of a TypeError that ends the whole task."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn

    takes_any = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
    arg_names = ", ".join(p.name for p in sig.parameters.values()
                          if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)) or "none"

    @functools.wraps(fn)
    def call(*args, **kwargs):
        unknown = [] if takes_any else [k for k in kwargs if k not in sig.parameters]
        try:
            if unknown:
                raise TypeError("unknown argument " + ", ".join(repr(k) for k in unknown))
            sig.bind(*args, **kwargs)
        except TypeError as e:
            return {"success": False,
                    "error": f"TypeError: wrong arguments for {name}: {e}. Its arguments are: {arg_names}."}
        return fn(*args, **kwargs)

    return call


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
            fn=checked(name, fn),
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