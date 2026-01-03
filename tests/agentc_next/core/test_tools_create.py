
import pytest
from pydantic_ai import ModelRetry
from agentc_next.core.tools import create_file

def test_create_file_success(tmp_path):
    # Set the current working directory to tmp_path for the test
    # (Since tools rely on CWD via _resolve_path)
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = create_file(None, "new_dir/new_file.txt", "content")
        assert result.success is True
        assert (tmp_path / "new_dir" / "new_file.txt").read_text(encoding="utf-8") == "content"
    finally:
        os.chdir(orig_cwd)


def test_create_file_exists_fails(tmp_path):
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        (tmp_path / "exists.txt").write_text("orig", encoding="utf-8")
        with pytest.raises(ModelRetry):
            create_file(None, "exists.txt", "new")
        assert (tmp_path / "exists.txt").read_text(encoding="utf-8") == "orig"
    finally:
        os.chdir(orig_cwd)


def test_create_file_outside_limit_fails(tmp_path):
    import os
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(ModelRetry):
            create_file(None, "../escaped.txt", "shady")
    finally:
        os.chdir(orig_cwd)
