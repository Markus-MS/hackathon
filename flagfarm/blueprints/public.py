from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template

from flagfarm.db import get_db
from flagfarm.services import ctf_service, leaderboard


bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    db = get_db()
    ctf = ctf_service.get_active_ctf(db)
    recent_ctfs = ctf_service.list_ctfs(db)

    if ctf is None:
        return render_template(
            "public/index.html",
            ctf=None,
            leaderboard_rows=[],
            matrix={"models": [], "rows": [], "solved_cells": 0, "total_cells": 0},
            overview={"challenge_count": 0, "model_count": 0, "running_count": 0},
            recent_ctfs=recent_ctfs,
        )

    return render_template(
        "public/index.html",
        ctf=ctf,
        leaderboard_rows=leaderboard.build_leaderboard(db, ctf["id"]),
        matrix=leaderboard.build_matrix(db, ctf["id"]),
        overview=leaderboard.build_ctf_overview(db, ctf["id"]),
        recent_ctfs=recent_ctfs,
    )


@bp.route("/ctfs/<int:ctf_id>")
def ctf_detail(ctf_id: int):
    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        abort(404)
    return render_template(
        "public/index.html",
        ctf=ctf,
        leaderboard_rows=leaderboard.build_leaderboard(db, ctf_id),
        matrix=leaderboard.build_matrix(db, ctf_id),
        overview=leaderboard.build_ctf_overview(db, ctf_id),
        recent_ctfs=ctf_service.list_ctfs(db),
    )


@bp.route("/healthz")
def healthz():
    db = get_db()
    ctf = ctf_service.get_active_ctf(db)
    return jsonify(
        {
            "ok": True,
            "active_ctf_id": ctf["id"] if ctf is not None else None,
        }
    )
