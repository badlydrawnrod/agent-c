from pathlib import Path
from unittest.mock import patch
from agentc.core.skill_loader import SkillLoader
from agentc.core.types import SkillMetadata

def test_skill_loader_discovery(tmp_path):
    # Create a mock skill directory structure
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    
    skill1_dir = skills_dir / "skill1"
    skill1_dir.mkdir()
    skill1_file = skill1_dir / "SKILL.md"
    skill1_file.write_text("""---
name: skill1
description: Skill 1 description
---
# Skill 1 Body
```bash
echo skill1
```
""", encoding="utf-8")
    
    skill2_dir = skills_dir / "skill2"
    skill2_dir.mkdir()
    skill2_file = skill2_dir / "SKILL.md"
    skill2_file.write_text("""---
name: skill2
description: Skill 2 description
---
# Skill 2 Body
""", encoding="utf-8")

    loader = SkillLoader()
    skills = loader.discover_skills([skills_dir])
    
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert "skill1" in names
    assert "skill2" in names

def test_skill_loader_parse_frontmatter():
    loader = SkillLoader()
    # Create a dummy path for the test
    dummy_path = Path("dummy/SKILL.md")
    
    # We need to mock the read_text call
    with patch("pathlib.Path.read_text") as mock_read:
        mock_read.return_value = """---
name: test-skill
description: Test skill description
---
# Body
"""
        skill = loader._parse_skill(dummy_path)
        
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "Test skill description"
        # Body is now empty as it's not kept in memory
        assert skill.body == ""

def test_get_skills_summary():
    loader = SkillLoader()
    skills = [
        SkillMetadata(
            name="skill1",
            description="Desc 1",
            path=Path("path/to/skill1"),
            body=""
        ),
        SkillMetadata(
            name="skill2",
            description="Desc 2",
            path=Path("path/to/skill2"),
            body=""
        )
    ]
    
    summary = loader.get_skills_summary(skills)
    assert "| Skill Name | Description | Base Directory | Documentation Path |" in summary
    assert "| skill1 | Desc 1 |" in summary
    # Check for normalized base directory
    assert "`path/to/skill1`" in summary.replace("\\", "/")
    # Check for normalized doc path
    assert "`path/to/skill1/SKILL.md`" in summary.replace("\\", "/")
    assert "\\" not in summary

def test_get_default_skill_dirs(tmp_path):
    loader = SkillLoader()
    
    # Mock Path.home() and platformdirs
    with patch("pathlib.Path.home", return_value=tmp_path / "home"), \
         patch("platformdirs.PlatformDirs") as mock_dirs:
        
        # Setup mock_dirs
        mock_instance = mock_dirs.return_value
        mock_instance.user_data_path = str(tmp_path / "appdata")
        
        # We also need to avoid the actual bundled skills installation which uses importlib.resources
        with patch.object(loader, "_install_default_skills", return_value=tmp_path / "bundled"):
            dirs = loader.get_default_skill_dirs()
            
            # Should have: [bundled, user, .github/skills, .claude/skills]
            assert len(dirs) == 4
            user_skill_dir = (tmp_path / "home" / ".agentc" / "skills")
            assert user_skill_dir in dirs
            assert user_skill_dir.exists()
