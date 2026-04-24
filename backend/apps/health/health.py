from backend.config.Apps import SubApp
from contextlib import asynccontextmanager
from fastapi.responses import PlainTextResponse
from typeguard import typechecked
from backend.debug import debug as debug_fn
from fastapi import status, HTTPException


@asynccontextmanager
async def health_lifespan():
    debug_fn("START")
    yield
    debug_fn("END")


health = SubApp("health", health_lifespan)

######################################
# Health Check Endpoints #
######################################


@health.router.get("/check")
@typechecked
async def check() -> PlainTextResponse:
    debug_fn("Health check successful")
    # Use PlainTextResponse instead of JSONResponse for AWS ALB compatibility
    # ALB health checks can be sensitive to JSON responses and Content-Length headers
    return PlainTextResponse(
        content="OK",
        status_code=status.HTTP_200_OK,
        headers={"Content-Type": "text/plain", "Content-Length": "2"},
    )
