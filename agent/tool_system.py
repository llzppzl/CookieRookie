"""
ToolSystem - plugin-style tool registry
"""

import functools
import inspect
import typing
from typing import Dict, Callable, Any, List, Optional
from dataclasses import dataclass


JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def schema_from_signature(fn: Callable) -> Dict[str, Any]:
    """A JSON Schema for a tool's arguments, built from its signature (for the API's tool use).
    Arguments without a default are required."""
    properties, required = {}, []
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}}
    for param in params:
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = param.annotation
        if typing.get_origin(annotation) is typing.Union:  # Optional[str]
            options = [a for a in typing.get_args(annotation) if a is not type(None)]
            annotation = options[0] if len(options) == 1 else None
        item_types = typing.get_args(annotation)
        annotation = typing.get_origin(annotation) or annotation  # List[str] -> list
        prop = {"type": JSON_TYPES.get(annotation, "string")}
        if prop["type"] == "array":
            prop["items"] = {"type": JSON_TYPES.get(item_types[0], "string") if item_types else "string"}
        properties[param.name] = prop
        if param.default is param.empty:
            required.append(param.name)
    return {"type": "object", "properties": properties, "required": required}


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
            fn=checked(name, fn),
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

    def api_tools(self, names=None) -> List[Dict[str, Any]]:
        """The tools (all, or only those in names) as tool definitions for the Messages API"""
        specs = []
        for tool in self._tools.values():
            if names is not None and tool.name not in names:
                continue
            description = tool.description or ((inspect.getdoc(tool.fn) or tool.name).splitlines() or [tool.name])[0]
            specs.append({
                "name": tool.name,
                "description": description,
                "input_schema": tool.args_schema or schema_from_signature(tool.fn),
            })
        return specs


# The shared instance
tool_system = ToolSystem()