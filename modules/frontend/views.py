from __future__ import annotations

import json
import time

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, stream_with_context, url_for
from werkzeug.routing import BuildError

from ctfarena.db import connect_db, get_db
from ctfarena.services import ctf_service, leaderboard, run_activity


frontend_bp = Blueprint(
    "frontend",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/frontend-static",
)


STATUS_KIND = {
    "solved": "solved",
    "running": "trying",
    "queued": "idle",
    "failed": "error",
    "crashed": "error",
    "budget_exhausted": "error",
    "timed_out": "error",
}
LIVE_CHALLENGE_STATUSES = {"queued", "running"}


@frontend_bp.get("/")
def index():
    return render_template(
        "index.html",
        dashboard_api_url=url_for("frontend.api_dashboard"),
    )


@frontend_bp.get("/ctfs/<int:ctf_id>")
def ctf_detail(ctf_id: int):
    db = get_db()
    if ctf_service.get_ctf(db, ctf_id) is None:
        abort(404)
    return render_template(
        "index.html",
        dashboard_api_url=url_for("frontend.api_dashboard_for_ctf", ctf_id=ctf_id),
    )


@frontend_bp.get("/details")
def details():
    return render_template(
        "details.html",
        challenge_api_url=None,
        details_api_url=url_for("frontend.api_details"),
    )


@frontend_bp.get("/ctfs/<int:ctf_id>/challenges/<int:challenge_id>/details")
def challenge_details(ctf_id: int, challenge_id: int):
    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        abort(404)
    challenge = db.execute(
        """
        SELECT id, name
        FROM challenges
        WHERE id = ? AND ctf_event_id = ?
        """,
        (challenge_id, ctf_id),
    ).fetchone()
    if challenge is None:
        abort(404)
    return render_template(
        "details.html",
        challenge_api_url=url_for("frontend.api_challenge_details", ctf_id=ctf_id, challenge_id=challenge_id),
        details_api_url=url_for("frontend.api_details"),
    )


@frontend_bp.get("/api/dashboard")
def api_dashboard():
    return jsonify(build_dashboard_payload())


@frontend_bp.get("/api/dashboard/<int:ctf_id>")
def api_dashboard_for_ctf(ctf_id: int):
    return jsonify(build_dashboard_payload(ctf_id))


@frontend_bp.get("/api/details")
def api_details():
    db = get_db()
    recent_ctfs = [serialize_recent_ctf(row) for row in ctf_service.list_ctfs(db)]
    ctf = ctf_service.get_active_ctf(db)
    if ctf is None:
        return jsonify(
            {
                "ctf": None,
                "summary": "No active CTF is configured.",
                "recent_ctfs": recent_ctfs,
            }
        )
    return jsonify(
        {
            "ctf": serialize_ctf(ctf),
            "overview": leaderboard.build_ctf_overview(db, ctf["id"]),
            "recent_ctfs": recent_ctfs,
        }
    )


@frontend_bp.get("/api/ctfs/<int:ctf_id>/challenges/<int:challenge_id>/details")
def api_challenge_details(ctf_id: int, challenge_id: int):
    return jsonify(build_challenge_details_payload(ctf_id=ctf_id, challenge_id=challenge_id))


@frontend_bp.get("/api/challenge-runs/<int:challenge_run_id>/activity")
def api_challenge_run_activity(challenge_run_id: int):
    after_id = request.args.get("after", type=int) or 0
    limit = min(400, max(1, request.args.get("limit", type=int) or 200))
    return jsonify(
        build_challenge_run_activity_payload(
            challenge_run_id,
            after_id=after_id,
            limit=limit,
        )
    )


@frontend_bp.get("/api/challenge-runs/<int:challenge_run_id>/activity/stream")
def api_challenge_run_activity_stream(challenge_run_id: int):
    after_id = request.args.get("after", type=int) or 0
    limit = min(400, max(1, request.args.get("limit", type=int) or 200))

    def generate():
        db = connect_db(current_app.config["DATABASE_PATH"])
        last_id = after_id
        idle_polls = 0
        try:
            while True:
                payload = _challenge_run_activity_payload_from_db(
                    db,
                    challenge_run_id,
                    after_id=last_id,
                    limit=limit,
                )
                if payload["events"]:
                    last_id = payload["events"][-1]["id"]
                    idle_polls = 0
                    yield f"data: {json.dumps(payload)}\n\n"
                    continue

                idle_polls += 1
                if payload["done"] and idle_polls >= 2:
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                yield ": keep-alive\n\n"
                time.sleep(1.0)
        finally:
            db.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@frontend_bp.get("/healthz")
def healthz():
    db = get_db()
    ctf = ctf_service.get_active_ctf(db)
    return jsonify(
        {
            "ok": True,
            "active_ctf_id": ctf["id"] if ctf is not None else None,
        }
    )


def build_dashboard_payload(ctf_id: int | None = None) -> dict[str, object]:
    if "DATABASE_PATH" not in current_app.config:
        return build_empty_dashboard_payload([])

    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id) if ctf_id is not None else ctf_service.get_active_ctf(db)
    recent_ctfs = [serialize_recent_ctf(row) for row in ctf_service.list_ctfs(db)]

    if ctf is None:
        return build_empty_dashboard_payload(recent_ctfs)

    matrix = leaderboard.build_matrix(db, ctf["id"])
    models = []
    for index, model in enumerate(matrix["models"]):
        cells = []
        for row in matrix["rows"]:
            challenge = row["challenge"]
            cell = row["cells"][index]
            status = str(cell["status"])
            cells.append(
                {
                    "challenge": challenge["name"],
                    "category": challenge["category"],
                    "points": challenge["points"],
                    "status": status,
                    "kind": STATUS_KIND.get(status, "idle"),
                    "label": status.replace("_", " "),
                    "cost_usd": cell["cost_usd"],
                    "solve_time_seconds": cell["solve_time_seconds"],
                    "error_message": cell["error_message"],
                }
            )
        models.append(
            {
                "name": model["display_name"],
                "slug": model["slug"],
                "color": model["color"],
                "states": [cell["kind"] for cell in cells],
                "cells": cells,
            }
        )

    payload = {
        "ctf": serialize_ctf(ctf),
        "status_text": f"Playing {ctf['title']} now" if ctf["status"] == "active" else f"{ctf['title']} is {ctf['status']}",
        "overview": leaderboard.build_ctf_overview(db, ctf["id"]),
        "challenges": [
            {
                "id": row["challenge"]["id"],
                "name": row["challenge"]["name"],
                "category": row["challenge"]["category"],
                "points": row["challenge"]["points"],
                "difficulty": row["challenge"]["difficulty"],
                "solves": row["challenge"]["solves"],
            }
            for row in matrix["rows"]
        ],
        "models": models,
        "leaderboard": leaderboard.build_leaderboard(db, ctf["id"]),
        "matrix": {
            "solved_cells": matrix["solved_cells"],
            "total_cells": matrix["total_cells"],
        },
        "recent_ctfs": recent_ctfs,
        "admin_url": safe_url_for("admin.dashboard"),
    }
    return payload


def build_empty_dashboard_payload(recent_ctfs: list[dict[str, object]]) -> dict[str, object]:
    return {
        "ctf": None,
        "status_text": "No active CTF is configured.",
        "overview": {
            "challenge_count": 0,
            "model_count": 0,
            "running_count": 0,
        },
        "challenges": [],
        "models": [],
        "leaderboard": [],
        "matrix": {
            "solved_cells": 0,
            "total_cells": 0,
        },
        "recent_ctfs": recent_ctfs,
        "admin_url": safe_url_for("admin.dashboard"),
    }


def build_challenge_details_payload(*, ctf_id: int, challenge_id: int) -> dict[str, object]:
    if "DATABASE_PATH" not in current_app.config:
        challenge = next((item for item in DEMO_CHALLENGES if int(item["id"]) == challenge_id), None)
        if challenge is None:
            abort(404)
        model_runs = []
        challenge_index = next((i for i, row in enumerate(DEMO_CHALLENGES) if int(row["id"]) == challenge_id), 0)
        for model in DEMO_MODELS:
            cell = model["cells"][challenge_index]
            status = str(cell["status"])
            model_runs.append(
                {
                    "model": model["name"],
                    "slug": model["slug"],
                    "provider": "OpenAI",
                    "color": model["color"],
                    "status": status,
                    "label": status.replace("_", " "),
                    "kind": STATUS_KIND.get(status, "idle"),
                    "cost_usd": 0.0,
                    "flag_attempts": 0,
                "turns": 0,
                "solve_time_seconds": None,
                "updated_at": None,
                "activity_api_url": None,
                "activity_stream_url": None,
                "terminal_text": "Demo mode: terminal stream is unavailable.",
            }
        )
        return {
            "ctf": {"id": 0, "title": "GlacierCTF", "status": "active"},
            "challenge": challenge,
            "models": model_runs,
        }

    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        abort(404)
    challenge = db.execute(
        """
        SELECT id, name, category, points, difficulty
        FROM challenges
        WHERE id = ? AND ctf_event_id = ?
        """,
        (challenge_id, ctf_id),
    ).fetchone()
    if challenge is None:
        abort(404)

    rows = db.execute(
        """
        SELECT
            mp.display_name,
            mp.slug,
            mp.provider,
            mp.color,
            chr.id AS challenge_run_id,
            cr.id AS competition_run_id,
            chr.status,
            chr.cost_usd,
            chr.flag_attempts,
            chr.turns,
            chr.solve_time_seconds,
            chr.updated_at,
            chr.transcript_excerpt,
            chr.error_message
        FROM competition_runs cr
        JOIN model_profiles mp ON mp.id = cr.model_id
        LEFT JOIN challenge_runs chr ON chr.competition_run_id = cr.id AND chr.challenge_id = ?
        WHERE cr.ctf_event_id = ?
        ORDER BY mp.display_name
        """,
        (challenge_id, ctf_id),
    ).fetchall()

    model_runs = []
    for row in rows:
        status = str(row["status"] or "queued")
        transcript = str(row["transcript_excerpt"] or "").strip()
        error_message = str(row["error_message"] or "").strip()
        terminal_text = transcript or error_message or "No terminal output yet."
        model_runs.append(
            {
                "model": row["display_name"],
                "slug": row["slug"],
                "provider": row["provider"],
                "color": row["color"],
                "challenge_run_id": row["challenge_run_id"],
                "competition_run_id": row["competition_run_id"],
                "status": status,
                "label": status.replace("_", " "),
                "kind": STATUS_KIND.get(status, "idle"),
                "cost_usd": float(row["cost_usd"] or 0),
                "flag_attempts": int(row["flag_attempts"] or 0),
                "turns": int(row["turns"] or 0),
                "solve_time_seconds": row["solve_time_seconds"],
                "updated_at": row["updated_at"],
                "activity_api_url": (
                    url_for("frontend.api_challenge_run_activity", challenge_run_id=row["challenge_run_id"])
                    if row["challenge_run_id"]
                    else None
                ),
                "activity_stream_url": (
                    url_for("frontend.api_challenge_run_activity_stream", challenge_run_id=row["challenge_run_id"])
                    if row["challenge_run_id"]
                    else None
                ),
                "terminal_text": terminal_text,
            }
        )

    return {
        "ctf": serialize_ctf(ctf),
        "challenge": dict(challenge),
        "models": model_runs,
    }


def build_challenge_run_activity_payload(
    challenge_run_id: int,
    *,
    after_id: int = 0,
    limit: int = 200,
) -> dict[str, object]:
    db = get_db()
    return _challenge_run_activity_payload_from_db(
        db,
        challenge_run_id,
        after_id=after_id,
        limit=limit,
    )


def _challenge_run_activity_payload_from_db(
    db,
    challenge_run_id: int,
    *,
    after_id: int,
    limit: int,
) -> dict[str, object]:
    row = db.execute(
        """
        SELECT id, status, updated_at
        FROM challenge_runs
        WHERE id = ?
        """,
        (challenge_run_id,),
    ).fetchone()
    if row is None:
        abort(404)

    events = [
        serialize_activity_event(item)
        for item in run_activity.list_activity(
            db,
            challenge_run_id,
            after_id=after_id,
            limit=limit,
        )
    ]
    return {
        "challenge_run_id": challenge_run_id,
        "status": row["status"],
        "updated_at": row["updated_at"],
        "done": str(row["status"]) not in LIVE_CHALLENGE_STATUSES,
        "events": events,
    }


def serialize_activity_event(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def serialize_ctf(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "ctfd_url": row["ctfd_url"],
        "sandbox_digest": row["sandbox_digest"],
        "budget_usd": row["budget_usd"],
        "budget_wall_seconds": row["budget_wall_seconds"],
    }


def serialize_recent_ctf(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "challenge_count": row["challenge_count"],
        "run_count": row["run_count"],
        "completed_runs": row["completed_runs"],
        "url": url_for("frontend.ctf_detail", ctf_id=row["id"]),
    }


def safe_url_for(endpoint: str, **values: object) -> str | None:
    try:
        return url_for(endpoint, **values)
    except BuildError:
        return None
