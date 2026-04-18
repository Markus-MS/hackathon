from __future__ import annotations

from dataclasses import dataclass

import requests

from flagfarm.utils import difficulty_from_points


class CTFdSyncError(RuntimeError):
    pass


@dataclass(slots=True)
class CTFdClient:
    base_url: str
    auth_value: str
    auth_type: str = "token"
    timeout: int = 15

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = "FlagFarm/0.1"
        if self.auth_value:
            if self.auth_type == "token":
                session.headers["Authorization"] = f"Token {self.auth_value}"
            elif self.auth_type == "bearer":
                session.headers["Authorization"] = f"Bearer {self.auth_value}"
            elif self.auth_type == "cookie":
                session.headers["Cookie"] = self.auth_value
        return session

    def fetch_challenges(self) -> list[dict[str, object]]:
        session = self._build_session()
        response = session.get(
            f"{self.base_url.rstrip('/')}/api/v1/challenges",
            timeout=self.timeout,
        )
        if not response.ok:
            raise CTFdSyncError(
                f"CTFd sync failed with {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        items = payload.get("data")
        if not isinstance(items, list):
            raise CTFdSyncError("Unexpected CTFd response shape.")

        challenges: list[dict[str, object]] = []
        for item in items:
            points = int(item.get("value") or 0)
            challenges.append(
                {
                    "remote_id": str(item["id"]),
                    "name": item.get("name") or f"challenge-{item['id']}",
                    "category": item.get("category") or "misc",
                    "points": points,
                    "difficulty": difficulty_from_points(points),
                    "description": item.get("description") or "",
                    "solves": int(item.get("solves") or 0),
                    "connection_info": item.get("connection_info") or "",
                }
            )
        return challenges
