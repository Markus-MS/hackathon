from __future__ import annotations

from flask import Blueprint, abort, jsonify

from flagfarm.db import get_db
from flagfarm.services import leaderboard
from flagfarm.services.competition import build_manifest, serialize_competition_run


bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/ctfs/<int:ctf_id>/leaderboard")
def leaderboard_json(ctf_id: int):
    db = get_db()
    return jsonify(leaderboard.build_leaderboard(db, ctf_id))


@bp.get("/competition-runs/<int:competition_run_id>")
def competition_run_json(competition_run_id: int):
    db = get_db()
    payload = serialize_competition_run(db, competition_run_id)
    if payload is None:
        abort(404)
    return jsonify(payload)


@bp.get("/competition-runs/<int:competition_run_id>/manifest")
def competition_manifest_json(competition_run_id: int):
    db = get_db()
    payload = build_manifest(db, competition_run_id)
    if payload is None:
        abort(404)
    return jsonify(payload)
