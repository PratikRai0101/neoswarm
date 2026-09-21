"""Hard-exit fuse for wedged shutdowns (ported from upstream `service/shutdown_fuse`).

If graceful shutdown has not finished FUSE_S seconds after it starts, the
fuse kills our descendant process tree and exits. A daemon thread is used so
a wedged event loop cannot block it.

The fuse is a no-op on Windows and inside the pytest suite (where a lifespan
exit must never detonate a timer mid-run).
"""

from __future__ import annotations

import os
import subprocess
import threading

FUSE_S = 10.0

_p_armed: threading.Timer | None = None


def _disabled() -> bool:
    return os.name == "nt" or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def p_descendant_pids() -> list[int]:
    pids: list[int] = []
    frontier: list[int] = [os.getpid()]
    for _ in range(6):
        next_frontier: list[int] = []
        for parent in frontier:
            try:
                out = subprocess.run(
                    ["pgrep", "-P", str(parent)],
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout
            except Exception:
                continue
            for tok in out.split():
                try:
                    next_frontier.append(int(tok))
                except ValueError:
                    pass
        pids.extend(next_frontier)
        if not next_frontier:
            break
        frontier = next_frontier
    return pids


def p_burn() -> None:
    for pid in p_descendant_pids():
        try:
            os.kill(pid, 9)
        except Exception:
            pass
    os._exit(0)


def arm_shutdown_fuse() -> None:
    """Call when lifespan shutdown STARTS. Never touches signal handlers."""
    global _p_armed
    if _disabled():
        return
    disarm_shutdown_fuse()
    _p_armed = threading.Timer(FUSE_S, p_burn)
    _p_armed.daemon = True
    _p_armed.start()


def fuse_armed() -> bool:
    return _p_armed is not None and not _p_armed.finished.is_set()


def disarm_shutdown_fuse() -> None:
    """Call when shutdown finished cleanly (or at startup to clear stale state)."""
    global _p_armed
    if _p_armed is not None:
        _p_armed.cancel()
        _p_armed = None
