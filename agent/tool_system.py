"""
ToolSystem - plugin-style tool registry
"""

from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDef:
    """A registered tool"""
    name: str
    fn: Callable
    confirmable: bool = False
    description: str = ""
    args_schema: Optional[Dict[str, Any]] = None


class ToolSystem:
    """Registers and looks up tools"""

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
        """Register a tool"""
        self._tools[name] = ToolDef(
            name=name,
            fn=fn,
            confirmable=confirmable,
            description=description,
            args_schema=args_schema
        )

    def get(self, name: str) -> Optional[ToolDef]:
        """Get a tool definition"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDef]:
        """List all tools"""
        return self._tools.copy()

    def is_confirmable(self, name: str) -> bool:
        """Whether the tool needs the user's confirmation"""
        tool = self._tools.get(name)
        return tool.confirmable if tool else False


# The shared instance
tool_system = ToolSystem()