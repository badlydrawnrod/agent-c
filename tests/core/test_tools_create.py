from unittest.mock import MagicMock
import pytest
from pydantic_ai import ModelRetry, RunContext
from agentc.core.tools import create_file
from agentc.core.types import RunDeps

def create_mock_context(tmp_path) -> RunContext[RunDeps]:
    ctx = MagicMock(spec=RunContext)
    ctx.deps = RunDeps(root_dirs=[tmp_path])
    return ctx

def test_create_file_success(tmp_path):
    # Set the current working directory to tmp_path for the test
    # (Since tools rely on CWD via _resolve_path)
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ctx = create_mock_context(tmp_path)
        result = create_file(ctx, "new_dir/new_file.txt", "content")
        assert result.success is True
        assert (tmp_path / "new_dir" / "new_file.txt").read_text(encoding="utf-8") == "content"
    finally:
        os.chdir(orig_cwd)


def test_create_file_exists_fails(tmp_path):
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ctx = create_mock_context(tmp_path)
        (tmp_path / "exists.txt").write_text("orig", encoding="utf-8")
        with pytest.raises(ModelRetry):
            create_file(ctx, "exists.txt", "new")
        assert (tmp_path / "exists.txt").read_text(encoding="utf-8") == "orig"
    finally:
        os.chdir(orig_cwd)


def test_create_file_outside_limit_fails(tmp_path):
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ctx = create_mock_context(tmp_path)
        with pytest.raises(ModelRetry):
            create_file(ctx, "../escaped.txt", "shady")
    finally:
        os.chdir(orig_cwd)
