"""Serve the API: `python -m api [--host 0.0.0.0] [--port 8000]` (PORT env var wins, for hosting)."""

from __future__ import annotations

import argparse
import os

import uvicorn

from api.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
