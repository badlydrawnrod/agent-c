from agentc.core.deps import RunDeps

def test_rundeps_consolidation(tmp_path):
    # Setup some dummy directories
    root = tmp_path / "root"
    child = root / "child"
    other = tmp_path / "other"
    skill = tmp_path / "skills"
    
    root.mkdir()
    child.mkdir()
    other.mkdir()
    skill.mkdir()
    
    # Initialize RunDeps with redundant paths
    deps = RunDeps(
        root_dirs=[root, child, other],
        skill_dirs=[skill, root]
    )
    
    # After __post_init__:
    # 1. skill_dirs are added to root_dirs: [root, child, other, skill, root]
    # 2. root_dirs consolidated: root (covers child), other, skill
    # 3. skill_dirs consolidated: skill, root (no overlap between these two specifically, but root covers child)
    
    # Root dirs should contain root, other, and skill (since skill was added)
    assert len(deps.root_dirs) == 3
    assert any(p.resolve() == root.resolve() for p in deps.root_dirs)
    assert any(p.resolve() == other.resolve() for p in deps.root_dirs)
    assert any(p.resolve() == skill.resolve() for p in deps.root_dirs)
    # child should be removed because it's a descendant of root
    assert not any(p.resolve() == child.resolve() for p in deps.root_dirs)
    
    # Skill dirs should contain skill and root
    assert len(deps.skill_dirs) == 2
    assert any(p.resolve() == skill.resolve() for p in deps.skill_dirs)
    assert any(p.resolve() == root.resolve() for p in deps.skill_dirs)

def test_rundeps_duplicates(tmp_path):
    path = tmp_path / "dir"
    path.mkdir()
    
    deps = RunDeps(
        root_dirs=[path, path],
        skill_dirs=[path]
    )
    
    assert len(deps.root_dirs) == 1
    assert len(deps.skill_dirs) == 1
    assert deps.root_dirs[0].resolve() == path.resolve()
