"""Local Git inspection and explicit commit operations."""

from __future__ import annotations

import asyncio
import re
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Query

from backend.apps.git.models import (
    GitBranch,
    GitCommitRequest,
    GitCommitResponse,
    GitDiff,
    GitStatus,
    GitStatusEntry,
)
from backend.config.Apps import SubApp

MAX_DIFF_BYTES = 120_000


class GitService:
    """A narrow, argument-list-only interface over the local Git executable."""

    @staticmethod
    def _directory(path: str) -> Path:
        directory = Path(path or ".").expanduser().resolve()
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Directory does not exist: {directory}")
        return directory

    @classmethod
    def _run(cls, path: str, *args: str, check: bool = True) -> str:
        directory = cls._directory(path)
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or "Git command failed"
            raise ValueError(detail)
        return result.stdout

    @classmethod
    def _status(cls, path: str) -> GitStatus:
        directory = cls._directory(path)
        root = Path(cls._run(str(directory), "rev-parse", "--show-toplevel").strip()).resolve()
        output = cls._run(str(directory), "status", "--porcelain=v1", "-b")
        lines = output.splitlines()
        header = lines[0][3:] if lines and lines[0].startswith("## ") else ""
        branch = header
        upstream = None
        ahead = behind = 0
        if "..." in header:
            branch, tracking = header.split("...", 1)
            match = re.match(r"(?P<upstream>[^ ]+)(?: \[(?P<details>[^]]+)\])?$", tracking)
            if match:
                upstream = match.group("upstream")
                details = match.group("details") or ""
                ahead_match = re.search(r"ahead (\d+)", details)
                behind_match = re.search(r"behind (\d+)", details)
                ahead = int(ahead_match.group(1)) if ahead_match else 0
                behind = int(behind_match.group(1)) if behind_match else 0
        elif header.startswith("No commits yet on "):
            branch = header.removeprefix("No commits yet on ")
        entries: list[GitStatusEntry] = []
        for line in lines[1:]:
            if len(line) < 3:
                continue
            payload = line[3:]
            original_path = None
            if " -> " in payload:
                original_path, payload = payload.split(" -> ", 1)
            entries.append(
                GitStatusEntry(
                    index=line[0],
                    worktree=line[1],
                    path=payload,
                    original_path=original_path,
                )
            )
        return GitStatus(
            path=str(directory),
            root=str(root),
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            clean=not entries,
            entries=entries,
        )

    @classmethod
    def _diff(cls, path: str, staged: bool) -> GitDiff:
        directory = cls._directory(path)
        args = ["diff", "--no-ext-diff", "--binary"]
        if staged:
            args.append("--cached")
        output = cls._run(str(directory), *args)
        truncated = len(output.encode("utf-8")) > MAX_DIFF_BYTES
        if truncated:
            encoded = output.encode("utf-8")[:MAX_DIFF_BYTES]
            output = encoded.decode("utf-8", errors="ignore")
        return GitDiff(path=str(directory), staged=staged, diff=output, truncated=truncated)

    @classmethod
    def _branches(cls, path: str) -> list[GitBranch]:
        directory = cls._directory(path)
        output = cls._run(
            str(directory),
            "for-each-ref",
            "--format=%(HEAD)\t%(refname:short)\t%(upstream:short)",
            "refs/heads",
        )
        return [
            GitBranch(name=parts[1], current=parts[0] == "*", upstream=parts[2] or None)
            for line in output.splitlines()
            if len(parts := line.split("\t")) == 3
        ]

    @classmethod
    def _commit(cls, request: GitCommitRequest) -> GitCommitResponse:
        directory = cls._directory(request.path)
        if request.stage_all:
            cls._run(str(directory), "add", "-A")
        cls._run(str(directory), "commit", "-m", request.message)
        commit = cls._run(str(directory), "rev-parse", "--short", "HEAD").strip()
        return GitCommitResponse(path=str(directory), commit=commit, message=request.message)

    async def status(self, path: str) -> GitStatus:
        return await asyncio.to_thread(self._status, path)

    async def diff(self, path: str, staged: bool = False) -> GitDiff:
        return await asyncio.to_thread(self._diff, path, staged)

    async def branches(self, path: str) -> list[GitBranch]:
        return await asyncio.to_thread(self._branches, path)

    async def commit(self, request: GitCommitRequest) -> GitCommitResponse:
        return await asyncio.to_thread(self._commit, request)



git_service = GitService()


@asynccontextmanager
async def git_lifespan():
    yield


git = SubApp("git", git_lifespan)


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@git.router.get("/status")
async def get_status(path: str = Query(".")):
    try:
        return {"status": (await git_service.status(path)).model_dump(mode="json")}
    except (OSError, ValueError) as exc:
        raise _error(exc) from exc


@git.router.get("/diff")
async def get_diff(path: str = Query("."), staged: bool = Query(False)):
    try:
        return {"diff": (await git_service.diff(path, staged)).model_dump(mode="json")}
    except (OSError, ValueError) as exc:
        raise _error(exc) from exc


@git.router.get("/branches")
async def get_branches(path: str = Query(".")):
    try:
        return {"branches": [branch.model_dump(mode="json") for branch in await git_service.branches(path)]}
    except (OSError, ValueError) as exc:
        raise _error(exc) from exc


@git.router.post("/commit")
async def create_commit(body: GitCommitRequest):
    try:
        return {"commit": (await git_service.commit(body)).model_dump(mode="json")}
    except (OSError, ValueError) as exc:
        raise _error(exc) from exc
