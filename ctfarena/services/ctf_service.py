from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlparse

from flask import current_app

from ctfarena.db import DELETED_MODEL_SLUGS_SETTING, get_setting, set_setting
from ctfarena.utils import slugify, utc_now

logger = logging.getLogger(__name__)


def list_models(db: sqlite3.Connection, *, enabled_only: bool = False):
    query = "SELECT * FROM model_profiles"
    params: tuple[object, ...] = ()
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY display_name"
    return db.execute(query, params).fetchall()


def get_model(db: sqlite3.Connection, model_id: int):
    return db.execute(
        "SELECT * FROM model_profiles WHERE id = ?",
        (model_id,),
    ).fetchone()


def delete_model(db: sqlite3.Connection, model_id: int):
    model = get_model(db, model_id)
    if model is None:
        return None

    _remember_deleted_model_slug(model["slug"])
    db.execute("DELETE FROM model_profiles WHERE id = ?", (model_id,))
    db.commit()
    return model


def _remember_deleted_model_slug(slug: str) -> None:
    try:
        existing = json.loads(get_setting(DELETED_MODEL_SLUGS_SETTING, "[]") or "[]")
    except ValueError:
        existing = []
    if not isinstance(existing, list):
        existing = []

    slugs = {str(item) for item in existing if str(item).strip()}
    slugs.add(slug)
    set_setting(DELETED_MODEL_SLUGS_SETTING, json.dumps(sorted(slugs)))


def list_ctfs(db: sqlite3.Connection):
    return db.execute(
        """
        SELECT
            c.*,
            (SELECT COUNT(*) FROM challenges ch WHERE ch.ctf_event_id = c.id) AS challenge_count,
            (SELECT COUNT(*) FROM competition_runs cr WHERE cr.ctf_event_id = c.id) AS run_count,
            (SELECT COUNT(*) FROM competition_runs cr WHERE cr.ctf_event_id = c.id AND cr.status = 'completed') AS completed_runs
        FROM ctf_events c
        ORDER BY datetime(c.created_at) DESC
        """
    ).fetchall()


def get_ctf(db: sqlite3.Connection, ctf_id: int):
    return db.execute(
        """
        SELECT
            c.*,
            (SELECT COUNT(*) FROM challenges ch WHERE ch.ctf_event_id = c.id) AS challenge_count,
            (SELECT COUNT(*) FROM competition_runs cr WHERE cr.ctf_event_id = c.id) AS run_count
        FROM ctf_events c
        WHERE c.id = ?
        """,
        (ctf_id,),
    ).fetchone()


def get_active_ctf(db: sqlite3.Connection):
    active_id = get_setting("active_ctf_id")
    if active_id:
        try:
            active_ctf_id = int(active_id)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid active_ctf_id setting: %r", active_id)
            set_setting("active_ctf_id", "")
        else:
            row = get_ctf(db, active_ctf_id)
            if row is not None:
                return row
            logger.warning("Ignoring stale active_ctf_id setting: %s", active_id)
            set_setting("active_ctf_id", "")
    return db.execute(
        """
        SELECT
            c.*,
            (SELECT COUNT(*) FROM challenges ch WHERE ch.ctf_event_id = c.id) AS challenge_count,
            (SELECT COUNT(*) FROM competition_runs cr WHERE cr.ctf_event_id = c.id) AS run_count
        FROM ctf_events c
        WHERE c.status = 'active'
        ORDER BY datetime(c.updated_at) DESC
        LIMIT 1
        """
    ).fetchone()


def create_ctf(db: sqlite3.Connection, payload: dict[str, object]) -> int:
    now = utc_now()
    title = str(payload["title"]).strip()
    slug_root = slugify(title) or f"ctf-{now[:10]}"
    slug = slug_root
    suffix = 2
    while db.execute("SELECT 1 FROM ctf_events WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug_root}-{suffix}"
        suffix += 1

    budget = current_app.config["DEFAULT_CTF_BUDGET"] | payload.get("budget", {})
    sandbox_digest = str(payload.get("sandbox_digest") or current_app.config["DEFAULT_SANDBOX_DIGEST"])
    prompt_template_hash = str(
        payload.get("prompt_template_hash")
        or current_app.config["DEFAULT_PROMPT_TEMPLATE_HASH"]
    )

    cursor = db.execute(
        """
        INSERT INTO ctf_events (
            title,
            slug,
            ctfd_url,
            ctfd_token,
            ctfd_auth_type,
            sandbox_digest,
            prompt_template_hash,
            budget_wall_seconds,
            budget_input_tokens,
            budget_output_tokens,
            budget_usd,
            budget_flag_attempts,
            flag_regex,
            mode,
            status,
            created_at,
            updated_at,
            started_at,
            ended_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'competition', 'draft', ?, ?, ?, ?)
        """,
        (
            title,
            slug,
            str(payload["ctfd_url"]).rstrip("/"),
            str(payload.get("ctfd_token") or ""),
            str(payload.get("ctfd_auth_type") or "token"),
            sandbox_digest,
            prompt_template_hash,
            int(budget["wall_seconds"]),
            int(budget["input_tokens"]),
            int(budget["output_tokens"]),
            float(budget["usd"]),
            int(budget["flag_attempts"]),
            str(payload.get("flag_regex") or r"flag\{.*?\}"),
            now,
            now,
            payload.get("started_at"),
            payload.get("ended_at"),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def activate_ctf(db: sqlite3.Connection, ctf_id: int):
    ctf = get_ctf(db, ctf_id)
    if ctf is None:
        raise ValueError(f"Unknown CTF #{ctf_id}.")

    now = utc_now()
    db.execute(
        "UPDATE ctf_events SET status = 'archived', updated_at = ? WHERE status = 'active' AND id != ?",
        (now, ctf_id),
    )
    db.execute(
        "UPDATE ctf_events SET status = 'active', updated_at = ? WHERE id = ?",
        (now, ctf_id),
    )
    db.commit()
    set_setting("active_ctf_id", str(ctf_id))
    logger.info("Activated CTF #%d (%s)", ctf_id, ctf["title"])
    return ctf


def delete_ctf(db: sqlite3.Connection, ctf_id: int):
    ctf = get_ctf(db, ctf_id)
    if ctf is None:
        return None

    db.execute("DELETE FROM ctf_events WHERE id = ?", (ctf_id,))
    db.commit()
    if get_setting("active_ctf_id") == str(ctf_id):
        set_setting("active_ctf_id", "")
        logger.info("Cleared active_ctf_id after deleting CTF #%d", ctf_id)
    return ctf


def list_ctf_accounts(db: sqlite3.Connection, ctf_id: int):
    return db.execute(
        """
        SELECT
            a.*,
            m.display_name,
            m.slug,
            m.color
        FROM ctf_accounts a
        JOIN model_profiles m ON m.id = a.model_id
        WHERE a.ctf_event_id = ?
        ORDER BY m.display_name
        """,
        (ctf_id,),
    ).fetchall()


def get_ctf_account(db: sqlite3.Connection, ctf_id: int, model_id: int):
    return db.execute(
        """
        SELECT
            a.*,
            m.display_name,
            m.slug
        FROM ctf_accounts a
        JOIN model_profiles m ON m.id = a.model_id
        WHERE a.ctf_event_id = ? AND a.model_id = ?
        """,
        (ctf_id, model_id),
    ).fetchone()


def upsert_ctf_account(
    db: sqlite3.Connection,
    *,
    ctf_id: int,
    model_id: int,
    username: str = "",
    password: str = "",
    api_token: str = "",
    team_name: str = "",
    notes: str = "",
) -> None:
    now = utc_now()
    db.execute(
        """
        INSERT INTO ctf_accounts (
            ctf_event_id,
            model_id,
            username,
            password,
            api_token,
            team_name,
            notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ctf_event_id, model_id) DO UPDATE SET
            username = excluded.username,
            password = excluded.password,
            api_token = excluded.api_token,
            team_name = excluded.team_name,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (ctf_id, model_id, username, password, api_token, team_name, notes, now, now),
    )
    db.commit()


def list_challenges(db: sqlite3.Connection, ctf_id: int):
    return db.execute(
        """
        SELECT *
        FROM challenges
        WHERE ctf_event_id = ?
        ORDER BY solves DESC, points ASC, name
        """,
        (ctf_id,),
    ).fetchall()


def list_challenge_files(db: sqlite3.Connection, challenge_id: int):
    return db.execute(
        """
        SELECT *
        FROM challenge_files
        WHERE challenge_id = ?
        ORDER BY display_name, id
        """,
        (challenge_id,),
    ).fetchall()


def upsert_challenges(
    db: sqlite3.Connection,
    *,
    ctf_id: int,
    challenges: list[dict[str, object]],
) -> None:
    now = utc_now()
    for challenge in challenges:
        db.execute(
            """
            INSERT INTO challenges (
                ctf_event_id,
                remote_id,
                name,
                category,
                points,
                difficulty,
                description,
                solves,
                connection_info,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ctf_event_id, remote_id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                points = excluded.points,
                difficulty = excluded.difficulty,
                description = excluded.description,
                solves = excluded.solves,
                connection_info = excluded.connection_info,
                updated_at = excluded.updated_at
            """,
            (
                ctf_id,
                str(challenge["remote_id"]),
                str(challenge["name"]),
                str(challenge.get("category") or "misc"),
                int(challenge.get("points") or 0),
                str(challenge.get("difficulty") or "medium"),
                str(challenge.get("description") or ""),
                int(challenge.get("solves") or 0),
                str(challenge.get("connection_info") or ""),
                now,
                now,
            ),
        )
        challenge_row = db.execute(
            """
            SELECT id
            FROM challenges
            WHERE ctf_event_id = ? AND remote_id = ?
            """,
            (ctf_id, str(challenge["remote_id"])),
        ).fetchone()
        if challenge_row is None:
            continue
        _replace_challenge_files(
            db,
            challenge_id=int(challenge_row["id"]),
            files=challenge.get("files") or [],
        )
    db.commit()


def _replace_challenge_files(
    db: sqlite3.Connection,
    *,
    challenge_id: int,
    files: object,
) -> None:
    db.execute("DELETE FROM challenge_files WHERE challenge_id = ?", (challenge_id,))
    if not isinstance(files, list):
        return

    used_names: set[str] = set()
    now = utc_now()
    for index, file_info in enumerate(files, start=1):
        if not isinstance(file_info, dict):
            continue
        remote_ref = str(file_info.get("remote_ref") or "").strip()
        download_url = str(file_info.get("download_url") or "").strip()
        if not remote_ref or not download_url:
            continue
        display_name = str(file_info.get("display_name") or "").strip() or _filename_from_url(
            download_url,
            fallback=f"challenge-file-{index}",
        )
        storage_name = _unique_storage_name(
            _safe_storage_name(display_name or f"challenge-file-{index}"),
            used_names,
        )
        metadata = file_info.get("metadata")
        db.execute(
            """
            INSERT INTO challenge_files (
                challenge_id,
                remote_ref,
                download_url,
                display_name,
                storage_name,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge_id,
                remote_ref,
                download_url,
                display_name,
                storage_name,
                json.dumps(metadata if isinstance(metadata, dict) else {}, sort_keys=True),
                now,
                now,
            ),
        )


def _filename_from_url(value: str, *, fallback: str) -> str:
    parsed = urlparse(value)
    name = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
    return name or fallback


def _safe_storage_name(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or "challenge-file"


def _unique_storage_name(value: str, used_names: set[str]) -> str:
    path = Path(value)
    stem = path.stem or "challenge-file"
    suffix = "".join(path.suffixes)
    candidate = value
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate
