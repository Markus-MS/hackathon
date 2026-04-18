from __future__ import annotations

import math
import sqlite3
import statistics


def compute_weighted_score(raw_points: int, total_cost_usd: float, budget_usd: float) -> float:
    epsilon = 0.01
    lambda_value = 0.1
    if raw_points <= 0:
        return 0.0
    efficiency_bonus = 1 + lambda_value * math.log1p((budget_usd or 1.0) / (total_cost_usd + epsilon))
    return round(raw_points * efficiency_bonus, 2)


def build_leaderboard(db: sqlite3.Connection, ctf_id: int) -> list[dict[str, object]]:
    rows = db.execute(
        """
        SELECT
            v.*,
            mp.display_name,
            mp.slug,
            mp.provider,
            mp.color
        FROM v_competition_scores v
        JOIN model_profiles mp ON mp.id = v.model_id
        WHERE v.ctf_event_id = ?
        ORDER BY mp.display_name
        """,
        (ctf_id,),
    ).fetchall()

    leaderboard: list[dict[str, object]] = []
    for row in rows:
        solve_times = [
            item["solve_time_seconds"]
            for item in db.execute(
                """
                SELECT solve_time_seconds
                FROM challenge_runs
                WHERE competition_run_id = ?
                    AND status = 'solved'
                    AND solve_time_seconds IS NOT NULL
                """,
                (row["competition_run_id"],),
            ).fetchall()
        ]
        p50 = round(statistics.median(solve_times), 1) if solve_times else None
        score = compute_weighted_score(
            int(row["raw_points"] or 0),
            float(row["total_usd"] or 0.0),
            float(row["budget_usd"] or 0.0),
        )
        solves = int(row["solves"] or 0)
        attempted = int(row["attempted"] or 0)
        total_usd = round(float(row["total_usd"] or 0.0), 4)

        leaderboard.append(
            {
                "competition_run_id": row["competition_run_id"],
                "model": row["display_name"],
                "model_slug": row["slug"],
                "provider": row["provider"],
                "color": row["color"],
                "status": row["status"],
                "score": score,
                "raw_points": int(row["raw_points"] or 0),
                "solves": solves,
                "attempted": attempted,
                "solve_rate": round((solves / attempted) * 100, 1) if attempted else 0.0,
                "p50_solve_time_seconds": p50,
                "total_usd": total_usd,
                "usd_per_flag": round(total_usd / solves, 4) if solves else None,
                "budget_exhausted": int(row["budget_exhausted"] or 0),
                "failed": int(row["failed"] or 0),
                "timed_out": int(row["timed_out"] or 0),
                "crashed": int(row["crashed"] or 0),
            }
        )

    leaderboard.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["solves"]),
            item["p50_solve_time_seconds"] if item["p50_solve_time_seconds"] is not None else float("inf"),
            item["model"],
        )
    )
    for index, row in enumerate(leaderboard, start=1):
        row["rank"] = index
    return leaderboard


def build_matrix(db: sqlite3.Connection, ctf_id: int) -> dict[str, object]:
    challenges = db.execute(
        """
        SELECT id, name, category, points, difficulty
        FROM challenges
        WHERE ctf_event_id = ?
        ORDER BY category, points DESC, name
        """,
        (ctf_id,),
    ).fetchall()
    models = db.execute(
        """
        SELECT
            cr.id AS competition_run_id,
            cr.status AS competition_status,
            mp.slug,
            mp.display_name,
            mp.color
        FROM competition_runs cr
        JOIN model_profiles mp ON mp.id = cr.model_id
        WHERE cr.ctf_event_id = ?
        ORDER BY mp.display_name
        """,
        (ctf_id,),
    ).fetchall()
    cells = db.execute(
        """
        SELECT
            chr.challenge_id,
            cr.id AS competition_run_id,
            mp.slug,
            chr.status,
            chr.cost_usd,
            chr.solve_time_seconds,
            chr.error_message
        FROM challenge_runs chr
        JOIN competition_runs cr ON cr.id = chr.competition_run_id
        JOIN model_profiles mp ON mp.id = cr.model_id
        WHERE cr.ctf_event_id = ?
        """,
        (ctf_id,),
    ).fetchall()

    by_cell = {
        (row["challenge_id"], row["slug"]): {
            "status": row["status"],
            "cost_usd": round(float(row["cost_usd"] or 0.0), 4),
            "solve_time_seconds": row["solve_time_seconds"],
            "error_message": row["error_message"],
        }
        for row in cells
    }

    rows: list[dict[str, object]] = []
    for challenge in challenges:
        row = {
            "challenge": {
                "id": challenge["id"],
                "name": challenge["name"],
                "category": challenge["category"],
                "points": challenge["points"],
                "difficulty": challenge["difficulty"],
            },
            "cells": [],
        }
        for model in models:
            row["cells"].append(
                {
                    "model_slug": model["slug"],
                    "model_name": model["display_name"],
                    "color": model["color"],
                    **by_cell.get(
                        (challenge["id"], model["slug"]),
                        {
                            "status": "queued",
                            "cost_usd": 0.0,
                            "solve_time_seconds": None,
                            "error_message": "",
                        },
                    ),
                }
            )
        rows.append(row)

    solved_cells = sum(1 for cell in by_cell.values() if cell["status"] == "solved")
    return {
        "models": [dict(model) for model in models],
        "rows": rows,
        "solved_cells": solved_cells,
        "total_cells": len(challenges) * len(models),
    }


def build_ctf_overview(db: sqlite3.Connection, ctf_id: int) -> dict[str, int]:
    challenge_count = db.execute(
        "SELECT COUNT(*) AS count FROM challenges WHERE ctf_event_id = ?",
        (ctf_id,),
    ).fetchone()["count"]
    model_count = db.execute(
        "SELECT COUNT(*) AS count FROM competition_runs WHERE ctf_event_id = ?",
        (ctf_id,),
    ).fetchone()["count"]
    running_count = db.execute(
        "SELECT COUNT(*) AS count FROM competition_runs WHERE ctf_event_id = ? AND status = 'running'",
        (ctf_id,),
    ).fetchone()["count"]
    return {
        "challenge_count": int(challenge_count),
        "model_count": int(model_count),
        "running_count": int(running_count),
    }
