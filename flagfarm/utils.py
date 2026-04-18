from __future__ import annotations

import re
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-")


def difficulty_from_points(points: int) -> str:
    if points <= 150:
        return "easy"
    if points <= 300:
        return "medium"
    if points <= 500:
        return "hard"
    return "insane"
