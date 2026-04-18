from __future__ import annotations

import concurrent.futures
import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass

import sentry_sdk
from flask import Flask, current_app

from flagfarm.db import get_db
from flagfarm.services import ctf_service, pricing
from flagfarm.utils import utc_now


TERMINAL_CHALLENGE_STATUSES = {
    "solved",
    "failed",
    "timed_out",
    "crashed",
    "budget_exhausted",
}

DIFFICULTY_FACTORS = {
    "easy": 0.92,
    "medium": 0.66,
    "hard": 0.44,
    "insane": 0.28,
}


@dataclass(slots=True)
class SolverResult:
    status: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cached_input_tokens: int
    flag_attempts: int
    turns: int
    solve_time_seconds: float | None
    transcript_excerpt: str
    error_message: str = ""


class SimulatedSolverBackend:
    def execute(self, *, ctf, model, challenge, account, competition_run) -> SolverResult:
        seed_material = (
            f"{ctf['id']}::{model['slug']}::{challenge['remote_id']}::{competition_run['id']}"
        )
        seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)

        point_scale = max(1.0, float(challenge["points"]) / 100.0)
        skill = float(model["skill_profile"])
        difficulty_factor = DIFFICULTY_FACTORS.get(challenge["difficulty"], 0.6)
        solve_probability = min(
            0.96,
            max(0.05, skill * difficulty_factor + rng.uniform(-0.08, 0.08)),
        )

        time.sleep(rng.uniform(0.03, 0.09))

        solved = rng.random() < solve_probability
        timed_out = not solved and rng.random() < 0.12
        crashed = not solved and not timed_out and rng.random() < 0.04

        input_tokens = int(rng.randint(18_000, 70_000) * point_scale)
        output_tokens = int(rng.randint(2_000, 9_000) * point_scale)
        reasoning_tokens = int(output_tokens * rng.uniform(0.3, 0.9))
        cached_input_tokens = int(input_tokens * rng.uniform(0.0, 0.2))
        turns = max(2, int(rng.randint(4, 14) * point_scale))
        flag_attempts = 1 if solved else rng.randint(1, competition_run["budget_flag_attempts"] + 1)
        solve_time_seconds = round(rng.uniform(40, 720) * point_scale, 1)

        account_name = account["username"] if account is not None else "missing-account"
        transcript_excerpt = (
            f"{model['display_name']} analyzed {challenge['name']} "
            f"with account {account_name} and sandbox {competition_run['sandbox_digest'][-12:]}."
        )

        status = "solved"
        if crashed:
            status = "crashed"
        elif timed_out:
            status = "timed_out"
        elif not solved:
            status = "failed"

        return SolverResult(
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
            flag_attempts=flag_attempts,
            turns=turns,
            solve_time_seconds=solve_time_seconds,
            transcript_excerpt=transcript_excerpt,
            error_message="" if status == "solved" else f"{status} during simulated solve",
        )


def _status_counts(db, competition_run_id: int) -> dict[str, int]:
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM challenge_runs
        WHERE competition_run_id = ?
        GROUP BY status
        """,
        (competition_run_id,),
    ).fetchall()
    return {row["status"]: row["count"] for row in rows}


def _refresh_run_totals(db, competition_run_id: int) -> None:
    totals = db.execute(
        """
        SELECT
            COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
            COALESCE(SUM(reasoning_tokens), 0) AS total_reasoning_tokens,
            COALESCE(SUM(cached_input_tokens), 0) AS total_cached_input_tokens,
            COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
            COALESCE(SUM(flag_attempts), 0) AS total_flag_attempts,
            COALESCE(SUM(turns), 0) AS total_turns
        FROM challenge_runs
        WHERE competition_run_id = ?
        """,
        (competition_run_id,),
    ).fetchone()

    now = utc_now()
    db.execute(
        """
        UPDATE competition_runs
        SET
            total_input_tokens = ?,
            total_output_tokens = ?,
            total_reasoning_tokens = ?,
            total_cached_input_tokens = ?,
            total_cost_usd = ?,
            total_flag_attempts = ?,
            total_turns = ?,
            summary_json = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            totals["total_input_tokens"],
            totals["total_output_tokens"],
            totals["total_reasoning_tokens"],
            totals["total_cached_input_tokens"],
            round(totals["total_cost_usd"], 4),
            totals["total_flag_attempts"],
            totals["total_turns"],
            json.dumps(_status_counts(db, competition_run_id), sort_keys=True),
            now,
            competition_run_id,
        ),
    )
    db.commit()


def _apply_budget(competition_run, result: SolverResult, cost_usd: float) -> tuple[str, str]:
    exceeded: list[str] = []
    if result.input_tokens > competition_run["budget_input_tokens"]:
        exceeded.append("input tokens")
    if result.output_tokens > competition_run["budget_output_tokens"]:
        exceeded.append("output tokens")
    if result.solve_time_seconds and result.solve_time_seconds > competition_run["budget_wall_seconds"]:
        exceeded.append("wall clock")
    if result.flag_attempts > competition_run["budget_flag_attempts"]:
        exceeded.append("flag attempts")
    if cost_usd > competition_run["budget_usd"]:
        exceeded.append("usd")

    if exceeded:
        reason = ", ".join(exceeded)
        message = result.error_message or f"Budget exhausted: {reason}"
        return "budget_exhausted", message
    return result.status, result.error_message


def create_competition_runs(db, ctf_id: int) -> list[int]:
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        raise ValueError("Unknown CTF.")

    models = ctf_service.list_models(db, enabled_only=True)
    if len(models) != 4:
        raise ValueError("FlagFarm competition mode expects exactly four enabled models.")

    challenges = ctf_service.list_challenges(db, ctf_id)
    if not challenges:
        raise ValueError("Sync or seed challenges before starting a competition.")

    missing_accounts = [
        model["display_name"]
        for model in models
        if ctf_service.get_ctf_account(db, ctf_id, model["id"]) is None
    ]
    if missing_accounts:
        raise ValueError(
            "Missing CTF accounts for: " + ", ".join(sorted(missing_accounts))
        )

    run_ids: list[int] = []
    now = utc_now()
    tool_name = "flagfarm-sim" if current_app.config["SIMULATE_SOLVER"] else "flagfarm"

    for model in models:
        existing = db.execute(
            """
            SELECT id
            FROM competition_runs
            WHERE ctf_event_id = ? AND model_id = ? AND mode = 'competition'
            """,
            (ctf_id, model["id"]),
        ).fetchone()

        if existing is None:
            cursor = db.execute(
                """
                INSERT INTO competition_runs (
                    ctf_event_id,
                    model_id,
                    mode,
                    tool,
                    model,
                    model_version,
                    sandbox_digest,
                    flagfarm_commit,
                    prompt_template_hash,
                    status,
                    budget_wall_seconds,
                    budget_input_tokens,
                    budget_output_tokens,
                    budget_usd,
                    budget_flag_attempts,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 'competition', ?, ?, '', ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctf_id,
                    model["id"],
                    tool_name,
                    model["model_name"],
                    ctf["sandbox_digest"],
                    current_app.config["FLAGFARM_COMMIT"],
                    ctf["prompt_template_hash"],
                    ctf["budget_wall_seconds"],
                    ctf["budget_input_tokens"],
                    ctf["budget_output_tokens"],
                    ctf["budget_usd"],
                    ctf["budget_flag_attempts"],
                    now,
                    now,
                ),
            )
            competition_run_id = int(cursor.lastrowid)
        else:
            competition_run_id = int(existing["id"])

        for challenge in challenges:
            db.execute(
                """
                INSERT OR IGNORE INTO challenge_runs (
                    competition_run_id,
                    challenge_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 'queued', ?, ?)
                """,
                (competition_run_id, challenge["id"], now, now),
            )

        run_ids.append(competition_run_id)

    db.commit()
    return run_ids


def get_competition_run(db, competition_run_id: int):
    return db.execute(
        """
        SELECT
            cr.*,
            mp.display_name,
            mp.slug,
            mp.provider,
            mp.rate_key,
            mp.reasoning_effort,
            mp.temperature,
            mp.color
        FROM competition_runs cr
        JOIN model_profiles mp ON mp.id = cr.model_id
        WHERE cr.id = ?
        """,
        (competition_run_id,),
    ).fetchone()


def serialize_competition_run(db, competition_run_id: int) -> dict[str, object] | None:
    run = get_competition_run(db, competition_run_id)
    if run is None:
        return None

    counts = _status_counts(db, competition_run_id)
    challenges = db.execute(
        """
        SELECT
            ch.name,
            ch.category,
            ch.points,
            chr.status,
            chr.cost_usd,
            chr.solve_time_seconds,
            chr.error_message
        FROM challenge_runs chr
        JOIN challenges ch ON ch.id = chr.challenge_id
        WHERE chr.competition_run_id = ?
        ORDER BY ch.category, ch.points DESC, ch.name
        """,
        (competition_run_id,),
    ).fetchall()

    return {
        "id": run["id"],
        "ctf_event_id": run["ctf_event_id"],
        "model": {
            "display_name": run["display_name"],
            "slug": run["slug"],
            "provider": run["provider"],
            "version": run["model"],
        },
        "status": run["status"],
        "tool": run["tool"],
        "started_at": run["started_at"],
        "ended_at": run["ended_at"],
        "budget": {
            "wall_seconds": run["budget_wall_seconds"],
            "input_tokens": run["budget_input_tokens"],
            "output_tokens": run["budget_output_tokens"],
            "usd": run["budget_usd"],
            "flag_attempts": run["budget_flag_attempts"],
        },
        "totals": {
            "input_tokens": run["total_input_tokens"],
            "output_tokens": run["total_output_tokens"],
            "reasoning_tokens": run["total_reasoning_tokens"],
            "cached_input_tokens": run["total_cached_input_tokens"],
            "cost_usd": run["total_cost_usd"],
            "flag_attempts": run["total_flag_attempts"],
            "turns": run["total_turns"],
        },
        "counts": counts,
        "challenges": [dict(row) for row in challenges],
    }


def build_manifest(db, competition_run_id: int) -> dict[str, object] | None:
    run = get_competition_run(db, competition_run_id)
    if run is None:
        return None

    ctf = ctf_service.get_ctf(db, run["ctf_event_id"])
    rate = pricing.get_rate(run["rate_key"])
    return {
        "competition_run_id": run["id"],
        "ctf": {
            "id": ctf["id"],
            "title": ctf["title"],
            "ctfd_url": ctf["ctfd_url"],
        },
        "sandbox_digest": run["sandbox_digest"],
        "flagfarm_commit": run["flagfarm_commit"],
        "prompt_template_hash": run["prompt_template_hash"],
        "tool": run["tool"],
        "model": run["model"],
        "model_profile": run["display_name"],
        "model_params": {
            "provider": run["provider"],
            "reasoning_effort": run["reasoning_effort"],
            "temperature": run["temperature"],
        },
        "budget": {
            "wall_seconds": run["budget_wall_seconds"],
            "input_tokens": run["budget_input_tokens"],
            "output_tokens": run["budget_output_tokens"],
            "usd": run["budget_usd"],
            "flag_attempts": run["budget_flag_attempts"],
        },
        "rate_card": rate,
    }


class CompetitionManager:
    def __init__(self, app: Flask) -> None:
        self.app = app
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=app.config["RUNNER_MAX_WORKERS"],
            thread_name_prefix="flagfarm-competition",
        )
        self._lock = threading.Lock()
        self._futures: dict[int, concurrent.futures.Future[None]] = {}
        self.backend = SimulatedSolverBackend()

    def start_ctf(self, ctf_id: int, *, synchronous: bool = False) -> list[int]:
        with self.app.app_context():
            db = get_db()
            run_ids = create_competition_runs(db, ctf_id)

        if synchronous:
            for run_id in run_ids:
                self._run_single(run_id)
            return run_ids

        with self._lock:
            for run_id in run_ids:
                future = self._futures.get(run_id)
                if future is not None and not future.done():
                    continue
                self._futures[run_id] = self.executor.submit(self._run_single, run_id)
        return run_ids

    def _run_single(self, competition_run_id: int) -> None:
        with self.app.app_context():
            db = get_db()
            competition_run = get_competition_run(db, competition_run_id)
            if competition_run is None:
                return
            if competition_run["status"] == "completed":
                return

            now = utc_now()
            db.execute(
                """
                UPDATE competition_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, competition_run_id),
            )
            db.commit()

            competition_run = get_competition_run(db, competition_run_id)
            ctf = ctf_service.get_ctf(db, competition_run["ctf_event_id"])
            model = ctf_service.get_model(db, competition_run["model_id"])
            account = ctf_service.get_ctf_account(db, ctf["id"], model["id"])
            challenges = ctf_service.list_challenges(db, ctf["id"])

            for challenge in challenges:
                challenge_run = db.execute(
                    """
                    SELECT *
                    FROM challenge_runs
                    WHERE competition_run_id = ? AND challenge_id = ?
                    """,
                    (competition_run_id, challenge["id"]),
                ).fetchone()
                if challenge_run is None or challenge_run["status"] in TERMINAL_CHALLENGE_STATUSES:
                    continue

                started_at = utc_now()
                db.execute(
                    """
                    UPDATE challenge_runs
                    SET
                        status = 'running',
                        attempt_index = 1,
                        started_at = COALESCE(started_at, ?),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (started_at, started_at, challenge_run["id"]),
                )
                db.commit()

                try:
                    result = self.backend.execute(
                        ctf=ctf,
                        model=model,
                        challenge=challenge,
                        account=account,
                        competition_run=competition_run,
                    )
                    cost_usd = pricing.estimate_cost(
                        model["rate_key"],
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cached_input_tokens=result.cached_input_tokens,
                        reasoning_tokens=result.reasoning_tokens,
                    )
                    final_status, final_error = _apply_budget(
                        competition_run,
                        result,
                        cost_usd,
                    )
                    ended_at = utc_now()
                    db.execute(
                        """
                        UPDATE challenge_runs
                        SET
                            status = ?,
                            ended_at = ?,
                            input_tokens = ?,
                            output_tokens = ?,
                            reasoning_tokens = ?,
                            cached_input_tokens = ?,
                            cost_usd = ?,
                            flag_attempts = ?,
                            turns = ?,
                            solve_time_seconds = ?,
                            transcript_excerpt = ?,
                            error_message = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            final_status,
                            ended_at,
                            result.input_tokens,
                            result.output_tokens,
                            result.reasoning_tokens,
                            result.cached_input_tokens,
                            cost_usd,
                            result.flag_attempts,
                            result.turns,
                            result.solve_time_seconds if final_status == "solved" else None,
                            result.transcript_excerpt,
                            final_error,
                            ended_at,
                            challenge_run["id"],
                        ),
                    )
                    db.commit()
                    _refresh_run_totals(db, competition_run_id)
                except Exception as exc:
                    sentry_sdk.capture_exception(exc)
                    ended_at = utc_now()
                    db.execute(
                        """
                        UPDATE challenge_runs
                        SET
                            status = 'crashed',
                            ended_at = ?,
                            error_message = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (ended_at, str(exc), ended_at, challenge_run["id"]),
                    )
                    db.commit()
                    _refresh_run_totals(db, competition_run_id)

            finished_at = utc_now()
            db.execute(
                """
                UPDATE competition_runs
                SET status = 'completed', ended_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (finished_at, finished_at, competition_run_id),
            )
            db.commit()
            _refresh_run_totals(db, competition_run_id)
