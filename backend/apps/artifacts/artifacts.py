from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.apps.artifacts.models import Artifact
from backend.config.Apps import SubApp
from backend.config.paths import ARTIFACTS_DIR

MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
_MEDIA_TYPE_OVERRIDES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".log": "text/plain",
    ".text": "text/plain",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
}
_ARTIFACT_ID = re.compile(r"^[a-f0-9]{32}$")


@asynccontextmanager
async def artifacts_lifespan():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    yield


artifacts = SubApp("artifacts", artifacts_lifespan)


def _metadata_path(artifact_id: str) -> Path:
    if not _ARTIFACT_ID.fullmatch(artifact_id):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return Path(ARTIFACTS_DIR) / f"{artifact_id}.json"


def _content_filename(artifact: Artifact) -> str:
    suffix = Path(artifact.filename).suffix.lower()
    if suffix and re.fullmatch(r"\.[a-z0-9]{1,16}", suffix):
        return f"{artifact.id}{suffix}"
    return f"{artifact.id}.bin"


def _content_candidates(artifact: Artifact) -> list[Path]:
    current = Path(ARTIFACTS_DIR) / _content_filename(artifact)
    legacy = Path(ARTIFACTS_DIR) / f"{artifact.id}.bin"
    return [current] if current == legacy else [current, legacy]


def _load(artifact_id: str) -> Artifact:
    metadata_path = _metadata_path(artifact_id)
    if not metadata_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        return Artifact(**json.loads(metadata_path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Artifact metadata is invalid") from exc


def _serialize(artifact: Artifact) -> dict[str, Any]:
    value = artifact.model_dump()
    value["content_url"] = f"/api/artifacts/{artifact.id}/content"
    value["download_url"] = f"/api/artifacts/{artifact.id}/download"
    return value


def _safe_filename(value: str, fallback: str) -> str:
    filename = Path(value).name.strip() if value else ""
    if not filename or filename in {".", ".."}:
        filename = fallback
    return filename[:255]


def _store_artifact(artifact: Artifact, *, content: bytes | None = None, source: Path | None = None) -> Artifact:
    root = Path(ARTIFACTS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    content_path = root / _content_filename(artifact)
    metadata_path = root / f"{artifact.id}.json"
    try:
        if content is not None:
            content_path.write_bytes(content)
        elif source is not None:
            shutil.copyfile(source, content_path)
        else:
            raise ValueError("Artifact content is required")
        metadata_path.write_text(
            json.dumps(artifact.model_dump(), indent=2), encoding="utf-8"
        )
    except Exception:
        content_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise
    return artifact


def publish_file(
    source_path: str | os.PathLike[str],
    *,
    name: str | None = None,
    description: str = "",
) -> Artifact:
    """Copy a local file into the user-controlled artifact store."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Artifact source is not a regular file: {source}")

    size_bytes = source.stat().st_size
    if size_bytes > MAX_ARTIFACT_BYTES:
        raise ValueError(
            f"Artifact is too large ({size_bytes} bytes); maximum is {MAX_ARTIFACT_BYTES} bytes"
        )

    filename = _safe_filename(name or source.name, source.name)
    media_type = _MEDIA_TYPE_OVERRIDES.get(
        source.suffix.lower(),
        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
    )
    artifact = Artifact(
        name=filename,
        description=description.strip(),
        filename=filename,
        media_type=media_type,
        size_bytes=size_bytes,
    )
    return _store_artifact(artifact, source=source)


def publish_bytes(
    content: bytes,
    *,
    name: str,
    media_type: str,
    description: str = "",
) -> Artifact:
    """Store generated or downloaded bytes in the local artifact workspace."""
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError(
            f"Artifact is too large ({len(content)} bytes); maximum is {MAX_ARTIFACT_BYTES} bytes"
        )
    filename = _safe_filename(name, "artifact.bin")
    artifact = Artifact(
        name=filename,
        description=description.strip(),
        filename=filename,
        media_type=media_type,
        size_bytes=len(content),
    )
    return _store_artifact(artifact, content=content)


def _all() -> list[Artifact]:
    root = Path(ARTIFACTS_DIR)
    if not root.is_dir():
        return []
    artifacts_list: list[Artifact] = []
    for metadata_path in root.glob("*.json"):
        try:
            artifacts_list.append(
                Artifact(**json.loads(metadata_path.read_text(encoding="utf-8")))
            )
        except (OSError, ValueError):
            continue
    return sorted(artifacts_list, key=lambda item: item.created_at, reverse=True)


def _content_response(artifact: Artifact, *, download: bool) -> FileResponse:
    content_path = next((path for path in _content_candidates(artifact) if path.is_file()), None)
    if content_path is None:
        raise HTTPException(status_code=404, detail="Artifact content not found")
    filename = artifact.filename.replace('"', "_").replace("\r", "").replace("\n", "")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        content_path,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@artifacts.router.get("/list")
async def list_artifacts():
    return {"artifacts": [_serialize(item) for item in _all()]}


@artifacts.router.get("/{artifact_id}/content")
async def serve_artifact(artifact_id: str):
    return _content_response(_load(artifact_id), download=False)


@artifacts.router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    return _content_response(_load(artifact_id), download=True)


@artifacts.router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    return _serialize(_load(artifact_id))


@artifacts.router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str):
    artifact = _load(artifact_id)
    _metadata_path(artifact.id).unlink(missing_ok=True)
    for content_path in _content_candidates(artifact):
        content_path.unlink(missing_ok=True)
    return {"ok": True}
