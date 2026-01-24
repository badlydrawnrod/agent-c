"""Tests for file editing tools (read_file, create_file, edit_file, apply_hunks)."""

import json
from unittest.mock import MagicMock

import pytest
from pydantic_ai import ModelRetry, RunContext

from agentc.core.backends.pydantic_ai.tools.editing import (
    read_file,
    create_file,
    edit_file,
    apply_hunks,
)
from agentc.core.deps import RunDeps
from agentc.core.types import FilePatch, PatchHunk, PatchPlan


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


# read_file tests
def test_read_file_directory_rejected(tmp_path, mock_ctx):
    with pytest.raises(ModelRetry):
        read_file(mock_ctx, ".")


def test_read_file_formats_with_line_numbers(tmp_path, mock_ctx):
    target = tmp_path / "data.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(mock_ctx, str(target))

    assert result.success is True
    assert result.content.splitlines() == [
        "     1\talpha",
        "     2\tbeta",
    ]
    assert result.content.endswith("\n")


def test_read_file_non_utf8_raises_modelretry(tmp_path, mock_ctx):
    target = tmp_path / "bin.dat"
    target.write_bytes(b"\xff\xfe")

    with pytest.raises(ModelRetry):
        read_file(mock_ctx, str(target))


# create_file tests
def test_create_file_success(tmp_path, mock_ctx):
    result = create_file(mock_ctx, "new_dir/new_file.txt", "content")
    assert result.success is True
    assert (tmp_path / "new_dir" / "new_file.txt").read_text(encoding="utf-8") == "content"


def test_create_file_exists_fails(tmp_path, mock_ctx):
    (tmp_path / "exists.txt").write_text("orig", encoding="utf-8")
    with pytest.raises(ModelRetry):
        create_file(mock_ctx, "exists.txt", "new")
    assert (tmp_path / "exists.txt").read_text(encoding="utf-8") == "orig"


def test_create_file_outside_limit_fails(tmp_path, mock_ctx):
    with pytest.raises(ModelRetry):
        create_file(mock_ctx, "../escaped.txt", "shady")


# edit_file tests
def test_edit_file_requires_unique_match_and_creates_backup(tmp_path, mock_ctx):
    target = tmp_path / "file.txt"
    target.write_text("one\none\n", encoding="utf-8")

    with pytest.raises(ModelRetry):
        edit_file(mock_ctx, str(target), "one", "ONE")

    target.write_text("only-once\n", encoding="utf-8")
    result = edit_file(mock_ctx, str(target), "only-once", "UPDATED")

    assert result.success is True
    assert "Edit completed" in result.content
    assert target.read_text(encoding="utf-8") == "UPDATED\n"

    backups = list(target.parent.glob("file.txt.bak.*"))
    assert len(backups) == 1


# apply_hunks tests
def test_apply_hunks_replaces_block(tmp_path, mock_ctx):
    target = tmp_path / "alpha.txt"
    target.write_text("alpha\nbravo\ncharlie\n", encoding="utf-8")

    plan = PatchPlan(
        files=[
            FilePatch(
                path=str(target),
                hunks=[
                    PatchHunk(
                        anchor_before=["alpha"],
                        remove=["bravo"],
                        add=["BRAVO"],
                        anchor_after=["charlie"],
                    )
                ],
            )
        ]
    )

    result = apply_hunks(mock_ctx, plan)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "alpha\nBRAVO\ncharlie\n"
    summary = json.loads(result.content)
    assert summary["applied"] is True


def test_apply_hunks_inserts_block(tmp_path, mock_ctx):
    target = tmp_path / "insert.txt"
    target.write_text("alpha\ncharlie\n", encoding="utf-8")

    plan = PatchPlan(
        files=[
            FilePatch(
                path=str(target),
                hunks=[
                    PatchHunk(
                        anchor_before=["alpha"],
                        remove=[],
                        add=["bravo"],
                        anchor_after=["charlie"],
                    )
                ],
            )
        ]
    )

    result = apply_hunks(mock_ctx, plan)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "alpha\nbravo\ncharlie\n"


def test_apply_hunks_no_match_does_not_modify(tmp_path, mock_ctx):
    target = tmp_path / "no-match.txt"
    original = "alpha\nbravo\ncharlie\n"
    target.write_text(original, encoding="utf-8")

    plan = PatchPlan(
        files=[
            FilePatch(
                path=str(target),
                hunks=[
                    PatchHunk(
                        anchor_before=["alpha"],
                        remove=["missing"],
                        add=["BRAVO"],
                        anchor_after=["charlie"],
                    )
                ],
            )
        ]
    )

    result = apply_hunks(mock_ctx, plan)

    assert result.success is False
    assert target.read_text(encoding="utf-8") == original


def test_apply_hunks_transactional_across_files(tmp_path, mock_ctx):
    file_one = tmp_path / "one.txt"
    file_two = tmp_path / "two.txt"
    file_one.write_text("one\n", encoding="utf-8")
    file_two.write_text("two\n", encoding="utf-8")

    plan = PatchPlan(
        files=[
            FilePatch(
                path=str(file_one),
                hunks=[
                    PatchHunk(
                        anchor_before=[],
                        remove=["one"],
                        add=["ONE"],
                        anchor_after=[],
                    )
                ],
            ),
            FilePatch(
                path=str(file_two),
                hunks=[
                    PatchHunk(
                        anchor_before=["two"],
                        remove=["missing"],
                        add=["TWO"],
                        anchor_after=[],
                    )
                ],
            ),
        ]
    )

    result = apply_hunks(mock_ctx, plan)

    assert result.success is False
    assert file_one.read_text(encoding="utf-8") == "one\n"
    assert file_two.read_text(encoding="utf-8") == "two\n"
