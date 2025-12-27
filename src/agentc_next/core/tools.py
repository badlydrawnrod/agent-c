"""
Tool implementations for Agent C Next.
"""
from pydantic_ai import RunContext

from .types import RunDeps


def list_files(ctx: RunContext[RunDeps], path: str = ".") -> str:
    """List files in the specified directory."""
    return "\n".join(sorted(["hello.py", "README.md", "data/"]))


def read_file(ctx: RunContext[RunDeps], path: str) -> str:
    """Read the contents of a text file and return cat -n style output."""
    return """\
     1\tdef hello_world():
     2\t    print("Hello, world!")
     3\t
    """


def edit_file(ctx: RunContext[RunDeps], path: str, old_str: str, new_str: str) -> str:
    """Edit a file by replacing old_str with new_str."""
    return "Edit completed successfully"
