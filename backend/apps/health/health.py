from contextlib import asynccontextmanager

from backend.config.Apps import SubApp
from backend.debug import debug as debug_fn


@asynccontextmanager
async def health_lifespan():
    debug_fn("START")
    yield
    debug_fn("END")


health = SubApp("health", health_lifespan)


@health.router.get("/check")
async def check() -> dict[str, str]:
    """Return the JSON health contract consumed by GUI, TUI, and scripts."""
    debug_fn("Health check successful")
    return {"status": "ok"}
