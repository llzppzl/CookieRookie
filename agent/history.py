"""
Keep the history the model reads from growing without limit.

The whole history is sent with every request, so on a long task the file contents, command
output and search results of every step add up until the request no longer fits the model's
context window. The last steps are sent in full; older steps keep what was done and whether it
worked, but drop the bulky parts. The model can read a file again if it needs it.
"""

# Steps at the end of the history that are sent in full
FULL_STEPS = 8

# Bulky fields dropped from the results and arguments of older steps
BULKY_RESULT_FIELDS = ("content", "stdout", "stderr", "matches", "source_content", "output")
BULKY_ARG_FIELDS = ("content", "new_string", "old_string")

# Longest error message kept for an older step
MAX_OLD_ERROR = 300


def _shorten(value) -> str:
    return f"[{len(str(value))} characters, not shown]"


def _compact_step(step: dict) -> dict:
    step = dict(step)
    action = step.get("action")
    if isinstance(action, dict) and isinstance(action.get("args"), dict):
        args = {k: _shorten(v) if k in BULKY_ARG_FIELDS and len(str(v)) > 80 else v
                for k, v in action["args"].items()}
        step["action"] = {**action, "args": args}
    result = step.get("result")
    if isinstance(result, dict):
        result = {k: v for k, v in result.items() if k not in BULKY_RESULT_FIELDS}
        error = result.get("error")
        if isinstance(error, str) and len(error) > MAX_OLD_ERROR:
            result["error"] = error[:MAX_OLD_ERROR] + "... [cut off]"
        step["result"] = result
    return step


def compact_history(context: dict, full_steps: int = FULL_STEPS) -> dict:
    """A copy of context in which only the last full_steps steps of the history keep their
    file contents, command output and search results. context itself is not changed."""
    history = context.get("history") or []
    if len(history) <= full_steps:
        return context
    split = len(history) - max(full_steps, 0)
    older, recent = history[:split], history[split:]
    return {**context, "history": [_compact_step(h) for h in older] + list(recent)}
