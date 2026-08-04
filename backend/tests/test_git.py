"""Git workspace service and native-tool behavior."""

import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.apps.agents.tools.base import ToolContext
from backend.apps.agents.tools.git import GitCommitTool, GitStatusTool
from backend.apps.git.git import GitService
from backend.apps.git.models import GitCommitRequest, GitPullRequestCreate, GitPushRequest
from backend.main import app


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
async def test_git_service_lists_remotes_and_pushes_explicitly(tmp_path):
    init_repo(tmp_path)
    remote = tmp_path.parent / "git-host.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", str(remote)], check=True)

    service = GitService()
    remotes = await service.remotes(str(tmp_path))
    assert remotes[0].name == "origin"
    assert remotes[0].url == str(remote)

    pushed = await service.push(GitPushRequest(path=str(tmp_path), remote="origin"))
    assert pushed.remote == "origin"
    assert pushed.branch
    assert "refs/heads" in subprocess.check_output(
        ["git", "--git-dir", str(remote), "show-ref"], text=True
    )


def test_git_http_api_exposes_remotes_and_explicit_push(tmp_path):
    init_repo(tmp_path)
    remote = tmp_path.parent / "git-http-remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", str(remote)], check=True)

    client = TestClient(app)
    remotes = client.get("/api/git/remotes", params={"path": str(tmp_path)})
    assert remotes.status_code == 200
    assert remotes.json()["remotes"][0]["name"] == "origin"

    pushed = client.post(
        "/api/git/push",
        json={"path": str(tmp_path), "remote": "origin", "set_upstream": True},
    )
    assert pushed.status_code == 200
    assert pushed.json()["push"]["branch"]


@pytest.mark.asyncio
async def test_git_service_creates_pull_request_through_explicit_gh_command(tmp_path, monkeypatch):
    init_repo(tmp_path)
    remote = tmp_path.parent / "git-host.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", str(remote)], check=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "gh-args.txt"
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{captured}'\n"
        "printf 'https://github.com/neoswarm/test/pull/7\\n'\n"
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{__import__('os').environ['PATH']}")

    result = await GitService().create_pull_request(
        GitPullRequestCreate(
            path=str(tmp_path),
            title="Add hosted workflow",
            body="Please review.",
            base="main",
            head="feature/hosted-git",
            draft=True,
        )
    )

    assert result.url == "https://github.com/neoswarm/test/pull/7"
    args = captured.read_text().splitlines()
    assert "pr" in args and "create" in args
    assert args[args.index("--title") + 1] == "Add hosted workflow"
    assert args[args.index("--body") + 1] == "Please review."
    assert "--draft" in args


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
