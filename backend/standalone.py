"""Entry point for NeoSwarm's bundled backend executable."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout

import uvicorn

os.environ.setdefault("NEOSWARM_PACKAGED", "1")


def _run_internal(name: str) -> None:
    if name == "browser-agent-mcp":
        from backend.apps.agents.browser_agent_mcp_server import main

        main()
        return
    if name == "invoke-agent-mcp":
        from backend.apps.agents.invoke_agent_mcp_server import main

        main()
        return
    if name == "python-exec":
        payload = json.loads(sys.stdin.read())
        capture = io.StringIO()
        namespace = {
            "input_data": payload.get("input_data", {}),
            "result": {},
        }
        with redirect_stdout(capture):
            exec(compile(payload.get("code", ""), "<neoswarm-output>", "exec"), namespace)
        json.dump(
            {
                "__stdout__": capture.getvalue(),
                "__result__": namespace.get("result", {}),
            },
            sys.stdout,
        )
        return
    raise ValueError(f"Unknown internal mode: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="NeoSwarm bundled backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("NEOSWARM_PORT", "8324"))
    )
    parser.add_argument(
        "--internal",
        choices=["browser-agent-mcp", "invoke-agent-mcp", "python-exec"],
    )
    args = parser.parse_args()

    if args.internal:
        _run_internal(args.internal)
        return

    from backend.main import app

    os.environ["NEOSWARM_PORT"] = str(args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
