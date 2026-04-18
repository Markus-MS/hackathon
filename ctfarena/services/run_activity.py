from __future__ import annotations

import json
import sqlite3

from ctfarena.utils import utc_now


def append_activity(
    db: sqlite3.Connection,
    challenge_run_id: int,
    *,
    kind: str,
    content: str,
    details: dict[str, object] | None = None,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO challenge_run_activity (
            challenge_run_id,
            kind,
            content,
            details_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            challenge_run_id,
            kind,
            content,
            json.dumps(details or {}, sort_keys=True),
            utc_now(),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def list_activity(
    db: sqlite3.Connection,
    challenge_run_id: int,
    *,
    after_id: int = 0,
    limit: int = 200,
):
    return db.execute(
        """
        SELECT *
        FROM challenge_run_activity
        WHERE challenge_run_id = ? AND id > ?
        ORDER BY id
        LIMIT ?
        """,
        (challenge_run_id, max(0, after_id), max(1, limit)),
    ).fetchall()


def clear_activity(db: sqlite3.Connection, challenge_run_id: int) -> None:
    db.execute(
        "DELETE FROM challenge_run_activity WHERE challenge_run_id = ?",
        (challenge_run_id,),
    )
    db.commit()


def upsert_artifact(
    db: sqlite3.Connection,
    challenge_run_id: int,
    *,
    name: str,
    text_content: str,
    content_type: str = "text/plain",
) -> None:
    now = utc_now()
    db.execute(
        """
        INSERT INTO challenge_run_artifacts (
            challenge_run_id,
            name,
            content_type,
            text_content,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(challenge_run_id, name) DO UPDATE SET
            content_type = excluded.content_type,
            text_content = excluded.text_content,
            updated_at = excluded.updated_at
        """,
        (
            challenge_run_id,
            name,
            content_type,
            text_content,
            now,
            now,
        ),
    )
    db.commit()


def list_artifacts(db: sqlite3.Connection, challenge_run_id: int):
    return db.execute(
        """
        SELECT *
        FROM challenge_run_artifacts
        WHERE challenge_run_id = ?
        ORDER BY name
        """,
        (challenge_run_id,),
    ).fetchall()


def clear_artifacts(db: sqlite3.Connection, challenge_run_id: int) -> None:
    db.execute(
        "DELETE FROM challenge_run_artifacts WHERE challenge_run_id = ?",
        (challenge_run_id,),
    )
    db.commit()
