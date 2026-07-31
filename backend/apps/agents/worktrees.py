"""Safe git-worktree isolation for agent sessions.

The manager owns worktree path/branch naming and deletion safety. Callers only
request an isolated checkout for a session or ask to clean one up; they never
construct destructive git commands themselves.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(RuntimeError):
    """A worktree operation could not be completed safely."""


class WorktreeDirtyError(WorktreeError):
    """A worktree with uncommitted changes requires explicit force removal."""


@dataclass(frozen=True)
class AgentWorktree:
    repo_root: str
    path: str
    branch: str


class GitWorktreeManager:
    """Create and remove NeoSwarm-owned worktrees below ``.worktrees``."""

    branch_prefix = "neoswarm/"
    directory_name = ".worktrees"

    async def create(self, base_path: str, session_id: str) -> AgentWorktree:
        source = Path(base_path).expanduser().resolve()
        if not source.is_dir():
            raise WorktreeError(f"Working directory does not exist: {source}")

        repo_root = Path(
            (await self._git(source, "rev-parse", "--show-toplevel")).strip()
        ).resolve()
        if not repo_root.is_dir():
            raise WorktreeError(f"Git repository was not found for: {source}")

        safe_id = "".join(char for char in session_id.lower() if char.isalnum())[:16]
        if not safe_id:
            raise WorktreeError("Session id cannot produce a safe worktree name")
        branch = f"{self.branch_prefix}{safe_id}"
        worktree_root = repo_root / self.directory_name
        worktree_path = (worktree_root / f"agent-{safe_id}").resolve()
        self._assert_owned_path(repo_root, worktree_path)
        if worktree_path.exists():
            raise WorktreeError(f"Agent worktree already exists: {worktree_path}")

        worktree_root.mkdir(parents=True, exist_ok=True)
        await self._git(
            repo_root,
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            "HEAD",
        )
        return AgentWorktree(
            repo_root=str(repo_root), path=str(worktree_path), branch=branch
        )

    async def is_dirty(self, worktree_path: str) -> bool:
        path = Path(worktree_path).expanduser().resolve()
        output = await self._git(path, "status", "--porcelain")
        return bool(output.strip())

    async def remove(
        self,
        repo_root: str,
        worktree_path: str,
        branch: str,
        *,
        force: bool = False,
    ) -> None:
        repo = Path(repo_root).expanduser().resolve()
        path = Path(worktree_path).expanduser().resolve()
        self._assert_owned_path(repo, path)
        if not branch.startswith(self.branch_prefix):
            raise WorktreeError(f"Refusing to delete non-NeoSwarm branch: {branch}")

        if path.exists() and await self.is_dirty(str(path)) and not force:
            raise WorktreeDirtyError(
                "Agent worktree contains uncommitted changes; use force removal explicitly"
            )

        if path.exists():
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(path))
            await self._git(repo, *args)
        else:
            await self._git(repo, "worktree", "prune")

        # The branch is NeoSwarm-owned and unique to this worktree. If removal
        # succeeded, delete it as part of the same cleanup operation.
        await self._git(repo, "branch", "-D", branch)

    def _assert_owned_path(self, repo_root: Path, worktree_path: Path) -> None:
        owned_root = (repo_root / self.directory_name).resolve()
        try:
            worktree_path.relative_to(owned_root)
        except ValueError as exc:
            raise WorktreeError(
                f"Refusing worktree operation outside {owned_root}: {worktree_path}"
            ) from exc
        if worktree_path == owned_root:
            raise WorktreeError("Refusing to operate on the worktree root itself")

    @staticmethod
    async def _git(cwd: Path, *args: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(cwd),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise WorktreeError("Git is required for worktree isolation") from exc

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise WorktreeError(detail or f"git {' '.join(args)} failed")
        return stdout.decode("utf-8", errors="replace")


worktree_manager = GitWorktreeManager()
