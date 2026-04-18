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

from flagfarm import create_app
from flagfarm.db import get_db
from flagfarm.services.demo import seed_demo_week


def main() -> None:
    app = create_app()
    with app.app_context():
        db = get_db()
        ctf_id = seed_demo_week(db)
        manager = app.extensions["competition_manager"]
        run_ids = manager.start_ctf(ctf_id, synchronous=True)
        print(f"Seeded demo week {ctf_id} with runs: {', '.join(str(run_id) for run_id in run_ids)}")


if __name__ == "__main__":
    main()
