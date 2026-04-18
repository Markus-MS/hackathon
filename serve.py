#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "flask>=3.1,<4",
#   "requests>=2.32,<3",
#   "sentry-sdk[flask]>=2.0,<3",
# ]
# ///

from __future__ import annotations

import os

from ctfarena import create_app


app = create_app()


def main() -> None:
    app.run(
        host=os.environ.get("CTF_ARENA_HOST", "127.0.0.1"),
        port=int(os.environ.get("CTF_ARENA_PORT", "8080")),
        debug=os.environ.get("CTF_ARENA_DEBUG", "").lower() in {"1", "true", "yes"},
    )


if __name__ == "__main__":
    main()
