"""
Tests for ToolResult type and tool functions returning ToolResult.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

from agentc.core.tools import (
    list_files,
    glob_paths,
    search_files,
    read_file,
    edit_file,
    run_command,
)
from agentc.core.types import RunDeps, ToolResult
from pydantic_ai import ModelRetry, RunContext


def create_mock_context(root_dirs: list[Path] | None = None) -> RunContext[RunDeps]:
    """Create a mock RunContext for testing."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = RunDeps(root_dirs=root_dirs or [])
    return ctx


class TestToolResultStructure:
    """Test that ToolResult has the expected structure."""

    def test_tool_result_success(self) -> None:
        """Test creating a successful ToolResult."""
        result = ToolResult(success=True, content="test content")
        assert result.success is True
        assert result.content == "test content"
        assert result.error is None

    def test_tool_result_failure(self) -> None:
        """Test creating a failed ToolResult."""
        result = ToolResult(success=False, content="", error="Something went wrong")
        assert result.success is False
        assert result.content == ""
        assert result.error == "Something went wrong"


class TestListFiles:
    """Tests for list_files tool."""

    def test_list_files_success(self, tmp_path: Path) -> None:
        """Test successful directory listing."""
        # Create test files in tmp_path
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Change to tmp_path, call list_files, then restore
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = list_files(ctx, ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "file1.txt" in result.content
            assert "file2.txt" in result.content
            assert "subdir/" in result.content
        finally:
            os.chdir(original_cwd)

    def test_list_files_empty_directory(self, tmp_path: Path) -> None:
        """Test listing an empty directory."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = list_files(ctx, ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "Directory is empty." in result.content
        finally:
            os.chdir(original_cwd)

    def test_list_files_invalid_path(self) -> None:
        """Test listing a non-existent path raises ModelRetry."""
        ctx = create_mock_context()
        try:
            result = list_files(ctx, "/nonexistent/path")
            # If it doesn't raise, check if it returns error ToolResult
            assert result.success is False
        except ModelRetry:
            # Expected behavior
            pass


class TestGlobPaths:
    """Tests for glob_paths tool."""

    def test_glob_paths_success(self, tmp_path: Path) -> None:
        """Test successful glob pattern matching."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("content")
        (tmp_path / "file3.txt").write_text("content")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = glob_paths(ctx, "*.txt", ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "file1.txt" in result.content
            assert "file3.txt" in result.content
            assert "file2.py" not in result.content
        finally:
            os.chdir(original_cwd)

    def test_glob_paths_no_matches(self, tmp_path: Path) -> None:
        """Test glob with no matches."""
        (tmp_path / "file.txt").write_text("content")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = glob_paths(ctx, "*.xyz", ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "No matches." in result.content
        finally:
            os.chdir(original_cwd)


class TestSearchFiles:
    """Tests for search_files tool."""

    def test_search_files_found(self, tmp_path: Path) -> None:
        """Test searching for existing content."""
        (tmp_path / "file1.txt").write_text("hello world\nfoo bar")
        (tmp_path / "file2.txt").write_text("goodbye world")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = search_files(ctx, "hello", ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "file1.txt" in result.content
            assert "hello world" in result.content
            assert "file2.txt" not in result.content
        finally:
            os.chdir(original_cwd)

    def test_search_files_not_found(self, tmp_path: Path) -> None:
        """Test searching for non-existent content."""
        (tmp_path / "file.txt").write_text("hello world")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = search_files(ctx, "xyz", ".")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "No matches." in result.content
        finally:
            os.chdir(original_cwd)


class TestReadFile:
    """Tests for read_file tool."""

    def test_read_file_success(self, tmp_path: Path) -> None:
        """Test reading a valid file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = read_file(ctx, "test.txt")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "line 1" in result.content
            assert "line 2" in result.content
            assert "line 3" in result.content
            # Check for line numbering
            assert "1\tline 1" in result.content
        finally:
            os.chdir(original_cwd)

    def test_read_file_not_found(self) -> None:
        """Test reading a non-existent file."""
        ctx = create_mock_context()
        try:
            result = read_file(ctx, "/nonexistent/file.txt")
            assert result.success is False
        except ModelRetry:
            pass


class TestEditFile:
    """Tests for edit_file tool."""

    def test_edit_file_success(self, tmp_path: Path) -> None:
        """Test successful file editing."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            result = edit_file(ctx, "test.txt", "original", "modified")

            assert isinstance(result, ToolResult)
            assert result.success is True
            assert "Edit completed successfully" in result.content
            assert test_file.read_text() == "modified content"
        finally:
            os.chdir(original_cwd)

    def test_edit_file_not_found(self, tmp_path: Path) -> None:
        """Test editing with content not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = create_mock_context([tmp_path])
            try:
                result = edit_file(ctx, "test.txt", "notfound", "replacement")
                assert result.success is False
            except ModelRetry:
                pass
        finally:
            os.chdir(original_cwd)


class TestRunCommand:
    """Tests for run_command tool."""

    def test_run_command_success(self) -> None:
        """Test successful command execution."""
        ctx = create_mock_context()
        result = asyncio.run(run_command(ctx, "echo hello"))

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "hello" in result.content

    def test_run_command_failure(self) -> None:
        """Test command execution failure."""
        ctx = create_mock_context()
        result = asyncio.run(run_command(ctx, "nonexistent_command_12345"))

        assert isinstance(result, ToolResult)
        assert result.success is False
