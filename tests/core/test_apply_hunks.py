import json
from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext

from agentc.core.tools import apply_hunks
from agentc.core.types import FilePatch, PatchHunk, PatchPlan, RunDeps


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


def test_apply_hunks_preserves_crlf_line_endings(tmp_path, mock_ctx):
    """Test that CRLF line endings are preserved after applying hunks."""
    target = tmp_path / "crlf.txt"
    target.write_text("alpha\r\nbravo\r\ncharlie\r\n", encoding="utf-8")

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
    assert target.read_text(encoding="utf-8") == "alpha\r\nBRAVO\r\ncharlie\r\n"


def test_apply_hunks_preserves_crlf_without_trailing_newline(tmp_path, mock_ctx):
    """Test that CRLF files without trailing newlines are preserved correctly."""
    target = tmp_path / "crlf_no_trail.txt"
    target.write_text("alpha\r\nbravo\r\ncharlie", encoding="utf-8")

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
    assert target.read_text(encoding="utf-8") == "alpha\r\nBRAVO\r\ncharlie"


def test_apply_hunks_preserves_lf_without_trailing_newline(tmp_path, mock_ctx):
    """Test that LF files without trailing newlines are preserved correctly."""
    target = tmp_path / "lf_no_trail.txt"
    target.write_text("alpha\nbravo\ncharlie", encoding="utf-8")

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
    assert target.read_text(encoding="utf-8") == "alpha\nBRAVO\ncharlie"
