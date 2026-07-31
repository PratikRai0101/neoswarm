"""Integration tests for safe agent git-worktree isolation."""

import subprocess
from pathlib import Path

import pytest

from backend.apps.agents.worktrees import (
    GitWorktreeManager,
    WorktreeDirtyError,
    WorktreeError,
)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "tests@neoswarm.local")
    git(repo, "config", "user.name", "NeoSwarm Tests")
    (repo / "README.md").write_text("initial\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
    return repo


@pytest.mark.asyncio
async def test_create_and_remove_owned_worktree(repository):
    manager = GitWorktreeManager()

    worktree = await manager.create(str(repository), "Session-ABC-123")

    path = Path(worktree.path)
    assert path.is_dir()
    assert path.parent == repository / ".worktrees"
    assert worktree.branch == "neoswarm/sessionabc123"
    assert git(path, "branch", "--show-current") == worktree.branch

    await manager.remove(worktree.repo_root, worktree.path, worktree.branch)

    assert not path.exists()
    assert worktree.branch not in git(repository, "branch", "--format=%(refname:short)")


@pytest.mark.asyncio
async def test_dirty_worktree_requires_explicit_force(repository):
    manager = GitWorktreeManager()
    worktree = await manager.create(str(repository), "dirty-session")
    Path(worktree.path, "notes.txt").write_text("uncommitted\n")

    with pytest.raises(WorktreeDirtyError, match="uncommitted changes"):
        await manager.remove(worktree.repo_root, worktree.path, worktree.branch)

    assert Path(worktree.path).exists()

    await manager.remove(
        worktree.repo_root,
        worktree.path,
        worktree.branch,
        force=True,
    )
    assert not Path(worktree.path).exists()


@pytest.mark.asyncio
async def test_remove_refuses_paths_and_branches_not_owned_by_neoswarm(repository):
    manager = GitWorktreeManager()

    with pytest.raises(WorktreeError, match="outside"):
        await manager.remove(str(repository), str(repository), "neoswarm/test")
    with pytest.raises(WorktreeError, match="non-NeoSwarm branch"):
        await manager.remove(
            str(repository),
            str(repository / ".worktrees" / "agent-test"),
            "main",
        )
