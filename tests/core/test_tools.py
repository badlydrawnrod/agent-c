import pytest
from pydantic_ai import ModelRetry

from agentc.core.tools import edit_file, glob_paths, list_files, read_file, search_files


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isolate tests to a temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_list_files_rejects_file(tmp_path):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(ModelRetry):
        list_files(None, str(tmp_path / "note.txt"))


def test_read_file_directory_rejected(tmp_path):
    with pytest.raises(ModelRetry):
        read_file(None, ".")


def test_read_file_formats_with_line_numbers(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(None, str(target))

    assert result.success is True
    assert result.content.splitlines() == [
        "     1\talpha",
        "     2\tbeta",
    ]
    assert result.content.endswith("\n")


def test_read_file_non_utf8_raises_modelretry(tmp_path):
    target = tmp_path / "bin.dat"
    target.write_bytes(b"\xff\xfe")

    with pytest.raises(ModelRetry):
        read_file(None, str(target))


def test_edit_file_requires_unique_match_and_creates_backup(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("one\none\n", encoding="utf-8")

    with pytest.raises(ModelRetry):
        edit_file(None, str(target), "one", "ONE")

    target.write_text("only-once\n", encoding="utf-8")
    result = edit_file(None, str(target), "only-once", "UPDATED")

    assert result.success is True
    assert "Edit completed" in result.content
    assert target.read_text(encoding="utf-8") == "UPDATED\n"

    backups = list(target.parent.glob("file.txt.bak.*"))
    assert len(backups) == 1


def test_glob_paths_basic(tmp_path):
    base = tmp_path / "root"
    (base / "d1").mkdir(parents=True)
    (base / "d1" / "a.txt").write_text("a", encoding="utf-8")
    (base / "b.txt").write_text("b", encoding="utf-8")

    result = glob_paths(None, "**/*.txt", path=str(base))
    lines = result.content.splitlines()

    # Should be relative to base and sorted
    assert lines == ["b.txt", "d1/a.txt"]


def test_glob_paths_truncates_results(tmp_path):
    base = tmp_path / "root"
    base.mkdir()
    for i in range(205):
        (base / f"f{i:03}.txt").write_text("x", encoding="utf-8")

    result = glob_paths(None, "*.txt", path=str(base))
    lines = result.content.splitlines()

    assert len(lines) == 201  # 200 results + summary line
    assert lines[-1].startswith("... 5 more")


def test_search_files_requires_directory(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("needle", encoding="utf-8")
    with pytest.raises(ModelRetry):
        search_files(None, "needle", path=str(file_path))


def test_search_files_finds_matches_sorted(tmp_path):
    base = tmp_path / "root"
    (base / "dir").mkdir(parents=True)
    (base / "dir" / "b.txt").write_text("alpha needle", encoding="utf-8")
    (base / "a.txt").write_text("needle beta", encoding="utf-8")

    result = search_files(None, "needle", path=str(base))
    lines = result.content.splitlines()

    assert lines == [
        "a.txt:1: needle beta",
        "dir/b.txt:1: alpha needle",
    ]


def test_search_files_truncates(tmp_path):
    base = tmp_path / "root"
    base.mkdir()
    big = base / "big.txt"
    big_lines = "\n".join(f"hit {i}" for i in range(205))
    big.write_text(big_lines, encoding="utf-8")

    result = search_files(None, "hit", path=str(base))
    lines = result.content.splitlines()

    assert len(lines) == 201  # 200 results + summary line
    assert lines[-1].startswith("... 5 more")