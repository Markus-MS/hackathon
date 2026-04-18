from __future__ import annotations

import sqlite3

from flask import current_app

from flagfarm.db import get_setting, set_setting
from flagfarm.utils import slugify, utc_now


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
        row = get_ctf(db, int(active_id))
        if row is not None:
            return row
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


def activate_ctf(db: sqlite3.Connection, ctf_id: int) -> None:
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
    username: str,
    password: str,
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
            team_name,
            notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ctf_event_id, model_id) DO UPDATE SET
            username = excluded.username,
            password = excluded.password,
            team_name = excluded.team_name,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (ctf_id, model_id, username, password, team_name, notes, now, now),
    )
    db.commit()


def list_challenges(db: sqlite3.Connection, ctf_id: int):
    return db.execute(
        """
        SELECT *
        FROM challenges
        WHERE ctf_event_id = ?
        ORDER BY category, points DESC, name
        """,
        (ctf_id,),
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
    db.commit()
