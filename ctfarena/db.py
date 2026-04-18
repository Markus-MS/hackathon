from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

from ctfarena.utils import utc_now

DELETED_MODEL_SLUGS_SETTING = "deleted_model_slugs"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
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
    migrate_db(db)
    db.commit()


def migrate_db(db: sqlite3.Connection) -> None:
    ctf_account_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(ctf_accounts)").fetchall()
    }
    if "api_token" not in ctf_account_columns:
        db.execute(
            "ALTER TABLE ctf_accounts ADD COLUMN api_token TEXT NOT NULL DEFAULT ''"
        )
        db.execute(
            """
            UPDATE ctf_accounts
            SET api_token = password
            WHERE api_token = '' AND password LIKE 'ctfd_%'
            """
        )


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
    db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, '[]')
        ON CONFLICT(key) DO NOTHING
        """,
        (DELETED_MODEL_SLUGS_SETTING,),
    )

    default_models = json.loads(
        Path(current_app.config["DEFAULT_MODEL_FILE"]).read_text(encoding="utf-8")
    )
    deleted_model_slugs = _deleted_model_slugs(db)
    now = utc_now()
    for model in default_models:
        if model["slug"] in deleted_model_slugs:
            continue
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

    from ctfarena.services import runtime_settings

    runtime_settings.seed_defaults(db)


def _deleted_model_slugs(db: sqlite3.Connection) -> set[str]:
    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        (DELETED_MODEL_SLUGS_SETTING,),
    ).fetchone()
    if row is None:
        return set()
    try:
        slugs = json.loads(row["value"])
    except (TypeError, ValueError):
        return set()
    if not isinstance(slugs, list):
        return set()
    return {str(slug) for slug in slugs if str(slug).strip()}


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        seed_reference_data()
