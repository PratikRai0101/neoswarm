"""Git workspace service and native-tool behavior."""

import json
import subprocess

import pytest

from backend.apps.agents.tools.base import ToolContext
from backend.apps.agents.tools.git import GitCommitTool, GitStatusTool
from backend.apps.git.git import GitService
from backend.apps.git.models import GitCommitRequest


def init_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "NeoSwarm Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@neoswarm.local"], check=True)
    (tmp_path / "README.md").write_text("initial\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "initial"], check=True)


@pytest.mark.asyncio
async def test_git_service_reports_diff_and_commit(tmp_path):
    init_repo(tmp_path)
    changed = tmp_path / "README.md"
    changed.write_text("changed\n")

    service = GitService()
    status = await service.status(str(tmp_path))
    assert status.branch
    assert status.clean is False
    assert status.entries[0].path == "README.md"

    diff = await service.diff(str(tmp_path))
    assert "-initial" in diff.diff
    assert "+changed" in diff.diff

    commit = await service.commit(
        GitCommitRequest(path=str(tmp_path), message="Update README", stage_all=True)
    )
    assert len(commit.commit) >= 7
    assert (await service.status(str(tmp_path))).clean is True


@pytest.mark.asyncio
async def test_git_service_parses_tracking_branch_counts(tmp_path):
    init_repo(tmp_path)
    remote = tmp_path.parent / "git-remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "push", "-qu", "origin", "HEAD"], check=True)
    (tmp_path / "README.md").write_text("ahead\n")

    status = await GitService().status(str(tmp_path))
    assert status.upstream
    assert status.ahead == 0
    assert status.behind == 0


@pytest.mark.asyncio
async def test_git_tools_use_agent_working_directory(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("note\n")
    context = ToolContext(cwd=str(tmp_path), session_id="git-test")

    status = json.loads((await GitStatusTool().execute({}, context))[0]["text"])
    assert status["entries"][0]["path"] == "notes.txt"

    result = json.loads(
        (await GitCommitTool().execute({"message": "Add notes", "stage_all": True}, context))[0]["text"]
    )
    assert result["message"] == "Add notes"
