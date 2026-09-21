"""Local service helpers (shutdown fuse, lifecycle guards)."""

from backend.apps.service.shutdown_fuse import (
    FUSE_S,
    arm_shutdown_fuse,
    disarm_shutdown_fuse,
    fuse_armed,
)

__all__ = [
    "FUSE_S",
    "arm_shutdown_fuse",
    "disarm_shutdown_fuse",
    "fuse_armed",
]
