import pytest
from agentc_next.core.tools import glob_paths, search_files

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Setup a workspace with some common files and directories."""
    monkeypatch.chdir(tmp_path)
    
    # Create git directory
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config", encoding="utf-8")
    
    # Create pycache
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "foo.pyc").write_text("bytecode", encoding="utf-8")
    
    # Create regular file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project", encoding="utf-8")
    
    return tmp_path

def test_defaults_ignored_in_glob(workspace):
    """Verify .git and __pycache__ are ignored by default in glob."""
    result = glob_paths(None, "**/*", path=".")
    lines = result.content.splitlines()
    
    # Should show src/ and README.md, but NOT .git or __pycache__
    assert "src/" in lines
    assert "src/main.py" in lines
    assert "README.md" in lines
    assert not any(line.startswith(".git/") for line in lines)
    assert not any(line.startswith("__pycache__/") for line in lines)

def test_defaults_ignored_in_search(workspace):
    """Verify .git contents are not searched."""
    # Search for 'git' which is in .git/config
    result = search_files(None, "git", path=".")
    
    # Should not find anything in .git
    assert result.content == "No matches."
    
    # Verify it finds content in README
    result = search_files(None, "Project", path=".")
    assert "README.md:1: # Project" in result.content

def test_gitignore_still_respected(workspace):
    """Verify .gitignore patterns are combined with defaults."""
    (workspace / ".gitignore").write_text("src/\n", encoding="utf-8")
    
    result = glob_paths(None, "**/*", path=".")
    lines = result.content.splitlines()
    
    # src/ should now be ignored due to .gitignore
    assert "src/" not in lines
    assert "src/main.py" not in lines
    # .git should still be ignored by default
    assert ".git/" not in lines
    # README.md should still be visible
    assert "README.md" in lines
    assert ".gitignore" in lines
