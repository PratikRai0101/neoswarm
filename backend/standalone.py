"""Entry point for NeoSwarm's bundled backend executable."""

import argparse
import os

import uvicorn

os.environ.setdefault("NEOSWARM_PACKAGED", "1")

from backend.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="NeoSwarm bundled backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("NEOSWARM_PORT", "8324"))
    )
    args = parser.parse_args()

    os.environ["NEOSWARM_PORT"] = str(args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
