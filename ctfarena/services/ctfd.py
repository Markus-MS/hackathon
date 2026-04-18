from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import unquote, urljoin, urlparse

import requests

from ctfarena.telemetry import metric_count, set_context, start_span
from ctfarena.utils import difficulty_from_points


class CTFdSyncError(RuntimeError):
    pass


class CTFdSubmitError(RuntimeError):
    pass


class CTFdDownloadError(RuntimeError):
    pass


FILE_LINK_RE = re.compile(r"""href=["']([^"'#?][^"']*)["']""", re.IGNORECASE)


def _is_correct_submission_response(data: dict[str, object]) -> bool:
    status = str(data.get("status") or "").strip().lower()
    if status:
        return status == "correct"

    message = str(data.get("message") or "").strip().lower()
    return message.strip(" .!:;") == "correct"


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
                    "files": self._collect_challenge_files(challenge),
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

    def _collect_challenge_files(self, challenge: dict[str, object]) -> list[dict[str, object]]:
        files: list[dict[str, object]] = []
        raw_files = challenge.get("files")
        if isinstance(raw_files, list):
            for index, item in enumerate(raw_files, start=1):
                normalized = self._normalize_file_entry(item, index=index)
                if normalized is not None:
                    files.append(normalized)

        description = str(challenge.get("description") or "")
        for url in self._extract_file_links(description):
            normalized = self._normalize_file_entry(url, index=len(files) + 1)
            if normalized is not None:
                files.append(normalized)

        deduped: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for item in files:
            key = (
                str(item.get("remote_ref") or "").strip(),
                str(item.get("download_url") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _normalize_file_entry(
        self,
        item: object,
        *,
        index: int,
    ) -> dict[str, object] | None:
        download_url = ""
        display_name = ""
        remote_ref = ""
        metadata: dict[str, object] = {}

        if isinstance(item, str):
            download_url = item.strip()
            metadata = {"source": "string"}
        elif isinstance(item, dict):
            metadata = dict(item)
            download_url = str(
                item.get("url")
                or item.get("location")
                or item.get("path")
                or item.get("href")
                or ""
            ).strip()
            display_name = str(
                item.get("name")
                or item.get("filename")
                or item.get("display_name")
                or item.get("title")
                or ""
            ).strip()
            remote_ref = str(
                item.get("id")
                or item.get("file_id")
                or item.get("uuid")
                or item.get("key")
                or ""
            ).strip()
        else:
            return None

        if not download_url:
            return None

        if not display_name:
            display_name = self._filename_from_url(download_url, fallback=f"challenge-file-{index}")
        if not remote_ref:
            remote_ref = download_url or display_name or f"challenge-file-{index}"

        return {
            "remote_ref": remote_ref,
            "download_url": download_url,
            "display_name": display_name,
            "metadata": metadata,
        }

    def _extract_file_links(self, description: str) -> list[str]:
        links: list[str] = []
        for match in FILE_LINK_RE.finditer(description):
            href = match.group(1).strip()
            if "/files/" not in href and "/plugins/" not in href:
                continue
            links.append(href)
        return links

    def _filename_from_url(self, value: str, *, fallback: str) -> str:
        parsed = urlparse(value)
        name = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
        return name or fallback

    def resolve_download_url(self, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            return value
        if value.startswith("//"):
            base = urlparse(self.base_url)
            return f"{base.scheme}:{value}"
        return urljoin(f"{self.base_url.rstrip('/')}/", value.lstrip("/"))

    def download_file(self, *, file_info: dict[str, object], destination_path) -> None:
        session = self._build_session()
        download_url = self.resolve_download_url(str(file_info.get("download_url") or ""))
        response = session.get(download_url, timeout=self.timeout, stream=True)
        if not response.ok:
            raise CTFdDownloadError(
                f"CTFd file download failed with {response.status_code}: {response.text[:200]}"
            )
        with open(destination_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)

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

        status = str(data.get("status") or "").strip().lower()
        message = str(data.get("message") or "")
        return {
            "correct": _is_correct_submission_response(data),
            "status": status,
            "message": message,
        }
