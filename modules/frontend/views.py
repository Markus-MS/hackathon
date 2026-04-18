from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, url_for
from werkzeug.routing import BuildError

from ctfarena.db import get_db
from ctfarena.services import ctf_service, leaderboard


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
    return render_template("details.html")


@frontend_bp.get("/api/dashboard")
def api_dashboard():
    return jsonify(build_dashboard_payload())


@frontend_bp.get("/api/dashboard/<int:ctf_id>")
def api_dashboard_for_ctf(ctf_id: int):
    return jsonify(build_dashboard_payload(ctf_id))


@frontend_bp.get("/api/details")
def api_details():
    db = get_db()
    ctf = ctf_service.get_active_ctf(db)
    if ctf is None:
        return jsonify({"ctf": None, "summary": "No active CTF is configured."})
    return jsonify(
        {
            "ctf": serialize_ctf(ctf),
            "overview": leaderboard.build_ctf_overview(db, ctf["id"]),
        }
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
