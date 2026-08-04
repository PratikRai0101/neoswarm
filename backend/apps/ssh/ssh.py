from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from backend.apps.ssh.models import SSHProfile, SSHProfileCreate, SSHProfileUpdate
from backend.config.Apps import SubApp
from backend.config.paths import SSH_PROFILES_DIR

_PROFILE_ID = re.compile(r"^[a-f0-9]{32}$")


class SSHService:
    """Persist non-secret SSH connection profiles and build safe argv lists."""

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @classmethod
    def _path(cls, profile_id: str) -> Path:
        if not _PROFILE_ID.fullmatch(profile_id):
            raise ValueError("Invalid SSH profile ID")
        return Path(SSH_PROFILES_DIR) / f"{profile_id}.json"

    @classmethod
    def _read(cls, profile_id: str) -> SSHProfile:
        path = cls._path(profile_id)
        if not path.is_file():
            raise ValueError("SSH profile not found")
        try:
            return SSHProfile(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise ValueError("SSH profile metadata is invalid") from exc

    @staticmethod
    def _serialize(profile: SSHProfile) -> dict:
        value = profile.model_dump()
        value["target"] = profile.target
        return value

    @classmethod
    def _save(cls, profile: SSHProfile) -> SSHProfile:
        root = Path(SSH_PROFILES_DIR)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{profile.id}.json").write_text(
            json.dumps(profile.model_dump(), indent=2), encoding="utf-8"
        )
        return profile

    def list(self) -> list[SSHProfile]:
        root = Path(SSH_PROFILES_DIR)
        if not root.is_dir():
            return []
        profiles: list[SSHProfile] = []
        for path in root.glob("*.json"):
            try:
                profiles.append(SSHProfile(**json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
        return sorted(profiles, key=lambda profile: profile.updated_at, reverse=True)

    def get(self, profile_id: str) -> SSHProfile:
        return self._read(profile_id)

    def create(self, request: SSHProfileCreate) -> SSHProfile:
        profile = SSHProfile(**request.model_dump())
        return self._save(profile)

    def update(self, profile_id: str, request: SSHProfileUpdate) -> SSHProfile:
        current = self._read(profile_id)
        values = current.model_dump()
        values.update(request.model_dump(exclude_unset=True))
        values["updated_at"] = self._now()
        return self._save(SSHProfile(**values))

    def delete(self, profile_id: str) -> None:
        path = self._path(profile_id)
        if not path.is_file():
            raise ValueError("SSH profile not found")
        path.unlink()

    @staticmethod
    def command(profile: SSHProfile) -> list[str]:
        destination = f"{profile.user}@{profile.host}" if profile.user else profile.host
        command = ["ssh", "-tt", "-p", str(profile.port)]
        if profile.identity_file:
            command.extend(["-i", profile.identity_file])
        command.append(destination)
        return command


ssh_service = SSHService()


@asynccontextmanager
async def ssh_lifespan():
    Path(SSH_PROFILES_DIR).mkdir(parents=True, exist_ok=True)
    yield


ssh = SubApp("ssh", ssh_lifespan)


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@ssh.router.get("/profiles")
async def list_profiles():
    return {"profiles": [SSHService._serialize(profile) for profile in ssh_service.list()]}


@ssh.router.post("/profiles", status_code=201)
async def create_profile(body: SSHProfileCreate):
    try:
        return SSHService._serialize(ssh_service.create(body))
    except ValueError as exc:
        raise _error(exc) from exc


@ssh.router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str):
    try:
        return SSHService._serialize(ssh_service.get(profile_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@ssh.router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: SSHProfileUpdate):
    try:
        return SSHService._serialize(ssh_service.update(profile_id, body))
    except ValueError as exc:
        raise _error(exc) from exc


@ssh.router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    try:
        ssh_service.delete(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
