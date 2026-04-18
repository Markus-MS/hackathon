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


DEMO_CHALLENGES = [
    {"id": 1, "name": "chall1", "category": "web", "points": 100, "difficulty": "easy"},
    {"id": 2, "name": "chall2", "category": "pwn", "points": 150, "difficulty": "easy"},
    {"id": 3, "name": "chall3", "category": "crypto", "points": 200, "difficulty": "medium"},
    {"id": 4, "name": "chall4", "category": "rev", "points": 250, "difficulty": "medium"},
    {"id": 5, "name": "chall5", "category": "forensics", "points": 300, "difficulty": "medium"},
    {"id": 6, "name": "chall6", "category": "misc", "points": 350, "difficulty": "medium"},
    {"id": 7, "name": "chall7", "category": "web", "points": 400, "difficulty": "hard"},
    {"id": 8, "name": "chall8", "category": "pwn", "points": 450, "difficulty": "hard"},
    {"id": 9, "name": "chall9", "category": "crypto", "points": 500, "difficulty": "hard"},
    {"id": 10, "name": "chall10", "category": "ai", "points": 550, "difficulty": "hard"},
]


DEMO_MODELS = [
    {
        "name": "gpt 5.4",
        "slug": "gpt-5-4",
        "color": "#34c759",
        "cells": [
            {"status": "solved", "kind": "solved"},
            {"status": "solved", "kind": "solved"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
        ],
    },
    {
        "name": "gpt 5.3",
        "slug": "gpt-5-3",
        "color": "#5ac8fa",
        "cells": [
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
        ],
    },
    {
        "name": "gpt 4.1",
        "slug": "gpt-4-1",
        "color": "#af52de",
        "cells": [
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
        ],
    },
    {
        "name": "gpt 4o",
        "slug": "gpt-4o",
        "color": "#ff9f0a",
        "cells": [
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "queued", "kind": "idle"},
        ],
    },
    {
        "name": "o4-mini",
        "slug": "o4-mini",
        "color": "#ff453a",
        "cells": [
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "queued", "kind": "idle"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "running", "kind": "trying"},
            {"status": "queued", "kind": "idle"},
            {"status": "solved", "kind": "solved"},
            {"status": "running", "kind": "trying"},
        ],
    },
]


DEMO_LEADERBOARD = [
    {
        "rank": 1,
        "model": "gpt 5.4",
        "provider": "OpenAI",
        "score": 1650,
        "solves": 8,
        "attempted": 10,
        "total_usd": 1.2842,
    },
    {
        "rank": 2,
        "model": "gpt 4.1",
        "provider": "OpenAI",
        "score": 1400,
        "solves": 7,
        "attempted": 10,
        "total_usd": 0.8739,
    },
    {
        "rank": 3,
        "model": "gpt 5.3",
        "provider": "OpenAI",
        "score": 1150,
        "solves": 6,
        "attempted": 10,
        "total_usd": 1.0465,
    },
    {
        "rank": 4,
        "model": "gpt 4o",
        "provider": "OpenAI",
        "score": 900,
        "solves": 4,
        "attempted": 10,
        "total_usd": 0.5127,
    },
    {
        "rank": 5,
        "model": "o4-mini",
        "provider": "OpenAI",
        "score": 850,
        "solves": 3,
        "attempted": 10,
        "total_usd": 0.2214,
    },
]


DEMO_RECENT_CTFS = [
    {
        "id": 101,
        "title": "AlpineCTF",
        "status": "completed",
        "challenge_count": 12,
        "run_count": 48,
        "completed_runs": 42,
        "url": "#archive-alpine",
    },
    {
        "id": 102,
        "title": "FrostbyteCTF",
        "status": "completed",
        "challenge_count": 9,
        "run_count": 35,
        "completed_runs": 31,
        "url": "#archive-frostbyte",
    },
    {
        "id": 103,
        "title": "SummitCTF",
        "status": "completed",
        "challenge_count": 15,
        "run_count": 62,
        "completed_runs": 55,
        "url": "#archive-summit",
    },
]


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
        return build_demo_dashboard_payload([])

    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id) if ctf_id is not None else ctf_service.get_active_ctf(db)
    recent_ctfs = [serialize_recent_ctf(row) for row in ctf_service.list_ctfs(db)]

    if ctf is None:
        return build_demo_dashboard_payload(recent_ctfs)

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
    if not payload["challenges"] or not payload["models"]:
        return build_demo_dashboard_payload(recent_ctfs)
    return payload


def build_demo_dashboard_payload(recent_ctfs: list[dict[str, object]]) -> dict[str, object]:
    models = []
    solved_cells = 0
    trying_cells = 0
    for model in DEMO_MODELS:
        cells = []
        for challenge, cell in zip(DEMO_CHALLENGES, model["cells"], strict=True):
            if cell["kind"] == "solved":
                solved_cells += 1
            elif cell["kind"] == "trying":
                trying_cells += 1
            cells.append(
                {
                    "challenge": challenge["name"],
                    "category": challenge["category"],
                    "points": challenge["points"],
                    "status": cell["status"],
                    "kind": cell["kind"],
                    "label": str(cell["status"]).replace("_", " "),
                    "cost_usd": None,
                    "solve_time_seconds": None,
                    "error_message": None,
                }
            )
        models.append(
            {
                "name": model["name"],
                "slug": model["slug"],
                "color": model["color"],
                "states": [cell["kind"] for cell in cells],
                "cells": cells,
            }
        )

    return {
        "ctf": {
            "id": 0,
            "title": "GlacierCTF",
            "status": "active",
            "ctfd_url": None,
            "sandbox_digest": "demo",
            "budget_usd": 25.0,
            "budget_wall_seconds": 14400,
        },
        "status_text": "Playing GlacierCTF now",
        "overview": {
            "challenge_count": len(DEMO_CHALLENGES),
            "model_count": len(models),
            "running_count": trying_cells,
        },
        "challenges": DEMO_CHALLENGES,
        "models": models,
        "leaderboard": DEMO_LEADERBOARD,
        "matrix": {
            "solved_cells": solved_cells,
            "total_cells": len(DEMO_CHALLENGES) * len(models),
        },
        "recent_ctfs": recent_ctfs or DEMO_RECENT_CTFS,
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
