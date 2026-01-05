import re
import shutil
from importlib.resources import as_file, files
from pathlib import Path

import platformdirs

from .config import DEFAULT_SKILL_DIRS
from .types import SkillMetadata

class SkillLoader:
    """Discovers and loads agent skills from multiple specialized directories."""

    def discover_skills(self, skills_dirs: list[Path]) -> list[SkillMetadata]:
        """
        Discover skills in the given directories.
        Each skill should be in its own subdirectory with a SKILL.md file.
        """
        skills: list[SkillMetadata] = []
        for skills_dir in skills_dirs:
            if not skills_dir.exists():
                continue

            for skill_path in skills_dir.iterdir():
                if skill_path.is_dir():
                    skill_file = skill_path / "SKILL.md"
                    if skill_file.exists():
                        skill = self._parse_skill(skill_file)
                        if skill:
                            skills.append(skill)
        return skills

    def get_default_skill_dirs(self) -> list[Path]:
        """Get the default list of skill directories, installing them if necessary."""
        return [self._install_default_skills(), self.get_user_skill_dir()] + DEFAULT_SKILL_DIRS

    def get_user_skill_dir(self) -> Path:
        """Get the user-defined, repository-independent skill directory."""
        path = Path.home() / ".agentc" / "skills"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _install_default_skills(self) -> Path:
        """Install the default configuration for Agent C Next."""
        dirs = platformdirs.PlatformDirs(
            appname="agentc", appauthor="badlydrawnrod", ensure_exists=True
        )
        config_path = Path(dirs.user_data_path)

        skills_path = config_path / "skills"
        skills_path.mkdir(parents=True, exist_ok=True)

        bundled_skills_dir = files("agentc") / "skills"
        with as_file(bundled_skills_dir) as src_path:
            shutil.copytree(src_path, skills_path, dirs_exist_ok=True)

        return skills_path

    def get_skills_summary(self, skills: list[SkillMetadata]) -> str:
        """Get a markdown table summary of available skills."""
        if not skills:
            return "No specialized skills available."
            
        lines = [
            "| Skill Name | Description | Base Directory | Documentation Path |",
            "| :--- | :--- | :--- | :--- |"
        ]
        for skill in skills:
            # Generate normalized relative paths using forward slashes for the LLM
            try:
                abs_base = skill.path.resolve()
                abs_skill_file = (skill.path / "SKILL.md").resolve()
                abs_cwd = Path.cwd().resolve()
                
                rel_base = abs_base.relative_to(abs_cwd)
                rel_doc = abs_skill_file.relative_to(abs_cwd)
            except ValueError:
                rel_base = skill.path
                rel_doc = skill.path / "SKILL.md"
            
            # Forward slashes are safer for LLMs and work cross-platform in Python
            base_str = str(rel_base).replace("\\", "/")
            doc_str = str(rel_doc).replace("\\", "/")
            lines.append(f"| {skill.name} | {skill.description} | `{base_str}` | `{doc_str}` |")
        
        return "\n".join(lines)

    def _parse_skill(self, skill_file: Path) -> SkillMetadata | None:
        """Parse a SKILL.md file for metadata."""
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            return None

        # Regex to match YAML frontmatter (between --- and ---)
        frontmatter_match = re.search(r"^---\s*\n(.*?)\n---\s*", content, re.DOTALL)
        if not frontmatter_match:
            return None

        frontmatter_str = frontmatter_match.group(1)

        metadata = {}
        for line in frontmatter_str.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        name = metadata.get("name")
        description = metadata.get("description")

        if name and description:
            return SkillMetadata(
                name=name,
                description=description,
                path=skill_file.parent,
                body=""  # Body no longer needed in memory
            )
        return None
