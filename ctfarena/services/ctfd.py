from __future__ import annotations

from dataclasses import dataclass

import requests

from ctfarena.telemetry import metric_count, set_context, start_span
from ctfarena.utils import difficulty_from_points


class CTFdSyncError(RuntimeError):
    pass


class CTFdSubmitError(RuntimeError):
    pass


@dataclass(slots=True)
class CTFdClient:
    base_url: str
    auth_value: str
    auth_type: str = "token"
    timeout: int = 15

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = "CTFArena/0.1 (+https://ctfarena.live/)"
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
        with start_span(
            op="ctfd.fetch",
            name="ctfd.fetch_challenges",
            attributes={"ctfd_url": self.base_url, "auth_type": self.auth_type},
        ):
            response = session.get(
                f"{self.base_url.rstrip('/')}/api/v1/challenges",
                timeout=self.timeout,
            )
        if not response.ok:
            metric_count("ctfarena.ctfd.fetch.error", 1, tags={"status_code": str(response.status_code)})
            raise CTFdSyncError(
                f"CTFd sync failed with {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        items = payload.get("data")
        if not isinstance(items, list):
            raise CTFdSyncError("Unexpected CTFd response shape.")

        challenges: list[dict[str, object]] = []
        for item in items:
            detail = self._fetch_challenge_detail(session, item["id"])
            challenge = item | detail
            points = int(challenge.get("value") or 0)
            challenges.append(
                {
                    "remote_id": str(challenge["id"]),
                    "name": challenge.get("name") or f"challenge-{challenge['id']}",
                    "category": challenge.get("category") or "misc",
                    "points": points,
                    "difficulty": difficulty_from_points(points),
                    "description": challenge.get("description") or "",
                    "solves": int(challenge.get("solves") or 0),
                    "connection_info": challenge.get("connection_info") or "",
                }
            )
        set_context("ctfd_fetch", {"challenge_count": len(challenges), "auth_type": self.auth_type})
        metric_count("ctfarena.ctfd.fetch.success", 1, tags={"auth_type": self.auth_type})
        return challenges

    def _fetch_challenge_detail(
        self,
        session: requests.Session,
        challenge_id: object,
    ) -> dict[str, object]:
        try:
            response = session.get(
                f"{self.base_url.rstrip('/')}/api/v1/challenges/{challenge_id}",
                timeout=self.timeout,
            )
        except requests.RequestException:
            return {}
        if not response.ok:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        data = payload.get("data")
        if not isinstance(data, dict):
            return {}
        return data

    def submit_flag(self, *, challenge_id: str, submission: str) -> dict[str, object]:
        session = self._build_session()
        with start_span(
            op="ctfd.submit",
            name="ctfd.submit_flag",
            attributes={"challenge_id": challenge_id, "auth_type": self.auth_type},
        ):
            response = session.post(
                f"{self.base_url.rstrip('/')}/api/v1/challenges/attempt",
                json={"challenge_id": int(challenge_id), "submission": submission},
                timeout=self.timeout,
            )
        if not response.ok:
            metric_count("ctfarena.ctfd.submit.error", 1, tags={"status_code": str(response.status_code)})
            raise CTFdSubmitError(
                f"CTFd submission failed with {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict):
            raise CTFdSubmitError("Unexpected CTFd submission response shape.")

        status = str(data.get("status") or "").lower()
        message = str(data.get("message") or "")
        message_lower = message.lower()
        return {
            "correct": (
                status in {"correct", "already_solved"}
                or "correct" in message_lower
                or ("already" in message_lower and "solved" in message_lower)
            ),
            "status": status,
            "message": message,
        }
