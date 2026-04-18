from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

from flagfarm.utils import utc_now


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_: object | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    db = get_db()
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    db.commit()


def seed_reference_data() -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ('active_ctf_id', '')
        ON CONFLICT(key) DO NOTHING
        """
    )

    default_models = json.loads(
        Path(current_app.config["DEFAULT_MODEL_FILE"]).read_text(encoding="utf-8")
    )
    now = utc_now()
    for model in default_models:
        db.execute(
            """
            INSERT INTO model_profiles (
                slug,
                display_name,
                provider,
                model_name,
                rate_key,
                color,
                reasoning_effort,
                temperature,
                skill_profile,
                enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                display_name = excluded.display_name,
                provider = excluded.provider,
                model_name = excluded.model_name,
                rate_key = excluded.rate_key,
                color = excluded.color,
                reasoning_effort = excluded.reasoning_effort,
                temperature = excluded.temperature,
                skill_profile = excluded.skill_profile,
                updated_at = excluded.updated_at
            """,
            (
                model["slug"],
                model["display_name"],
                model["provider"],
                model["model_name"],
                model["rate_key"],
                model["color"],
                model["reasoning_effort"],
                model["temperature"],
                model["skill_profile"],
                now,
                now,
            ),
        )
    db.commit()


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        seed_reference_data()
