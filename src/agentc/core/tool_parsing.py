"""
Utilities for parsing and normalizing tool arguments.
"""
from typing import Any


def parse_tool_args(args: Any) -> dict[str, Any]:
    """Parse tool call args into a dict, handling JSON strings."""
    if isinstance(args, dict):
        return args
    if args is None:
        return {}
    if isinstance(args, str):
        import json

        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"value": args}
    return {"value": str(args)}
