"""Pure patch application logic for structured hunks."""

from __future__ import annotations

from .types import FilePatch, FilePatchResult, HunkApplyResult, HunkMatchOptions, PatchHunk


def split_lines_with_newline(text: str) -> tuple[list[str], str, bool]:
    """Split text into lines while tracking newline style and trailing newline."""
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    return lines, newline, trailing_newline


def normalize_line(line: str, options: HunkMatchOptions | None) -> str:
    """Normalize a line according to match options."""
    if options and options.ignore_trailing_whitespace:
        return line.rstrip()
    return line


def sequence_matches(
    source: list[str],
    candidate: list[str],
    options: HunkMatchOptions | None,
) -> bool:
    """Return True if candidate lines match source lines under options."""
    if len(source) != len(candidate):
        return False
    return all(
        normalize_line(src, options) == normalize_line(cand, options)
        for src, cand in zip(source, candidate, strict=True)
    )


def find_hunk_matches(lines: list[str], hunk: PatchHunk) -> list[int]:
    """Find all starting indices where a hunk's match sequence occurs."""
    sequence = [*hunk.anchor_before, *hunk.remove, *hunk.anchor_after]
    if not sequence:
        return []
    options = hunk.match_options
    matches: list[int] = []
    limit = len(lines) - len(sequence) + 1
    for start in range(max(limit, 0)):
        window = lines[start : start + len(sequence)]
        if sequence_matches(window, sequence, options):
            matches.append(start)
    return matches


def select_match(matches: list[int], hunk: PatchHunk) -> int | None:
    """Select a match index, optionally using expected_near_line as a hint."""
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if hunk.expected_near_line is None:
        return None
    target = hunk.expected_near_line - 1
    best_distance = min(abs(match - target) for match in matches)
    closest = [match for match in matches if abs(match - target) == best_distance]
    if len(closest) == 1:
        return closest[0]
    return None


def apply_hunk(lines: list[str], hunk: PatchHunk) -> tuple[list[str], HunkApplyResult]:
    """Apply a hunk to lines and return updated lines with result info."""
    matches = find_hunk_matches(lines, hunk)
    chosen = select_match(matches, hunk)
    if chosen is None:
        if not matches:
            return lines, HunkApplyResult(index=0, applied=False, error="No match found")
        return (
            lines,
            HunkApplyResult(
                index=0,
                applied=False,
                error=(
                    "Multiple matches found; provide expected_near_line to disambiguate"
                ),
            ),
        )

    remove_start = chosen + len(hunk.anchor_before)
    remove_end = remove_start + len(hunk.remove)
    new_lines = [
        *lines[:remove_start],
        *hunk.add,
        *lines[remove_end:],
    ]
    return new_lines, HunkApplyResult(index=0, applied=True)


def apply_file_patch(
    file_patch: FilePatch, content: str
) -> tuple[str, FilePatchResult]:
    """Apply all hunks for a single file, returning updated content and result."""
    lines, newline, trailing_newline = split_lines_with_newline(content)
    hunk_results: list[HunkApplyResult] = []
    current_lines = lines

    for index, hunk in enumerate(file_patch.hunks):
        updated_lines, result = apply_hunk(current_lines, hunk)
        result.index = index
        hunk_results.append(result)
        if not result.applied:
            return content, FilePatchResult(
                path=file_patch.path,
                applied=False,
                hunks=hunk_results,
                error=result.error,
            )
        current_lines = updated_lines

    new_content = newline.join(current_lines)
    if trailing_newline:
        new_content += newline
    return new_content, FilePatchResult(
        path=file_patch.path,
        applied=True,
        hunks=hunk_results,
    )
