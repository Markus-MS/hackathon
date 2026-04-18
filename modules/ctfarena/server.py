#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "flask>=3.1,<4",
#   "flask-sock>=0.7,<1",
#   "requests>=2.32,<3",
#   "sentry-sdk[flask]>=2.0,<3",
# ]
# ///

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ctfarena import create_app


app = create_app()


def main() -> None:
    app.run(
        host=os.environ.get("FLAGFARM_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLAGFARM_PORT", "8080")),
        debug=os.environ.get("FLAGFARM_DEBUG", "").lower() in {"1", "true", "yes"},
    )


if __name__ == "__main__":
    main()
