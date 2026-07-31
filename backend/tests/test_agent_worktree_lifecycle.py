"""Agent lifecycle integration with git-worktree isolation."""

import subprocess
from pathlib import Path

import pytest

from backend.apps.agents.agent_manager import AgentManager
from backend.apps.agents.models import AgentConfig
from backend.apps.agents.worktrees import WorktreeDirtyError


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


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
async def test_agent_launches_in_worktree_and_dirty_delete_is_safe(repository):
    manager = AgentManager()
    session = await manager.launch_agent(
        AgentConfig(
            model="llama3.3",
            target_directory=str(repository),
            use_worktree=True,
        )
    )

    worktree_path = Path(session.worktree_path)
    assert session.cwd == session.worktree_path
    assert session.target_directory == str(repository)
    assert worktree_path.parent == repository / ".worktrees"
    assert session.branch_name.startswith("neoswarm/")

    (worktree_path / "new-file.txt").write_text("agent changes\n")
    with pytest.raises(WorktreeDirtyError):
        await manager.delete_session(session.id)

    assert session.id in manager.sessions
    assert worktree_path.exists()

    await manager.delete_session(session.id, force_worktree=True)

    assert session.id not in manager.sessions
    assert not worktree_path.exists()
