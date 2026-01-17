from agentc.core.patching.engine import apply_file_patch
from agentc.core.patching.types import FilePatch, PatchHunk


def test_apply_file_patch_preserves_crlf_and_trailing_newline() -> None:
    content = "alpha\r\nbravo\r\ncharlie\r\n"
    patch = FilePatch(
        path="/tmp/unused.txt",
        hunks=[
            PatchHunk(
                anchor_before=["alpha"],
                remove=["bravo"],
                add=["BRAVO"],
                anchor_after=["charlie"],
            )
        ],
    )

    updated, result = apply_file_patch(patch, content)

    assert result.applied is True
    assert updated == "alpha\r\nBRAVO\r\ncharlie\r\n"


def test_apply_file_patch_multiple_matches_requires_disambiguation() -> None:
    content = "alpha\nbravo\nalpha\nbravo\n"
    patch = FilePatch(
        path="/tmp/unused.txt",
        hunks=[
            PatchHunk(
                anchor_before=["alpha"],
                remove=["bravo"],
                add=["BRAVO"],
                anchor_after=[],
            )
        ],
    )

    updated, result = apply_file_patch(patch, content)

    assert result.applied is False
    assert result.error == (
        "Multiple matches found; provide expected_near_line to disambiguate"
    )
    assert updated == content


def test_apply_file_patch_disambiguates_expected_near_line() -> None:
    content = "alpha\nbravo\nalpha\nbravo\n"
    patch = FilePatch(
        path="/tmp/unused.txt",
        hunks=[
            PatchHunk(
                anchor_before=["alpha"],
                remove=["bravo"],
                add=["BRAVO"],
                anchor_after=[],
                expected_near_line=3,
            )
        ],
    )

    updated, result = apply_file_patch(patch, content)

    assert result.applied is True
    assert updated == "alpha\nbravo\nalpha\nBRAVO\n"


def test_apply_file_patch_no_match_returns_original() -> None:
    content = "alpha\nbravo\ncharlie\n"
    patch = FilePatch(
        path="/tmp/unused.txt",
        hunks=[
            PatchHunk(
                anchor_before=["alpha"],
                remove=["missing"],
                add=["BRAVO"],
                anchor_after=["charlie"],
            )
        ],
    )

    updated, result = apply_file_patch(patch, content)

    assert result.applied is False
    assert result.error == "No match found"
    assert updated == content
