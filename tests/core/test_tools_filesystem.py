"""Tests for filesystem discovery tools (list_files, glob_paths, search_files)."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import ModelRetry, RunContext

from agentc.core.tools.filesystem import glob_paths, list_files, search_files
from agentc.core.deps import RunDeps


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isolate tests to a temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def mock_ctx(tmp_path):
    """Create a mock RunContext with allowed root paths."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = RunDeps(root_dirs=[tmp_path])
    return ctx


def test_list_files_rejects_file(tmp_path, mock_ctx):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(ModelRetry):
        list_files(mock_ctx, str(tmp_path / "note.txt"))


def test_glob_paths_basic(tmp_path, mock_ctx):
    base = tmp_path / "root"
    (base / "d1").mkdir(parents=True)
    (base / "d1" / "a.txt").write_text("a", encoding="utf-8")
    (base / "b.txt").write_text("b", encoding="utf-8")

    result = glob_paths(mock_ctx, "**/*.txt", path=str(base))
    lines = result.content.splitlines()

    # Should be relative to base and sorted
    assert lines == ["b.txt", "d1/a.txt"]


def test_glob_paths_truncates_results(tmp_path, mock_ctx):
    base = tmp_path / "root"
    base.mkdir()
    for i in range(205):
        (base / f"f{i:03}.txt").write_text("x", encoding="utf-8")

    result = glob_paths(mock_ctx, "*.txt", path=str(base))
    lines = result.content.splitlines()

    assert len(lines) == 201  # 200 results + summary line
    assert lines[-1].startswith("... 5 more")


def test_search_files_requires_directory(tmp_path, mock_ctx):
    file_path = tmp_path / "file.txt"
    file_path.write_text("needle", encoding="utf-8")
    with pytest.raises(ModelRetry):
        search_files(mock_ctx, "needle", path=str(file_path))


def test_search_files_finds_matches_sorted(tmp_path, mock_ctx):
    base = tmp_path / "root"
    (base / "dir").mkdir(parents=True)
    (base / "dir" / "b.txt").write_text("alpha needle", encoding="utf-8")
    (base / "a.txt").write_text("needle beta", encoding="utf-8")

    result = search_files(mock_ctx, "needle", path=str(base))
    lines = result.content.splitlines()

    assert lines == [
        "a.txt:1: needle beta",
        "dir/b.txt:1: alpha needle",
    ]


def test_search_files_truncates(tmp_path, mock_ctx):
    base = tmp_path / "root"
    base.mkdir()
    big = base / "big.txt"
    big_lines = "\n".join(f"hit {i}" for i in range(205))
    big.write_text(big_lines, encoding="utf-8")

    result = search_files(mock_ctx, "hit", path=str(base))
    lines = result.content.splitlines()

    assert len(lines) == 201  # 200 results + summary line
    assert lines[-1].startswith("... 5 more")
