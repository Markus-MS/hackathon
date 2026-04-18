from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ctfarena.auth import admin_required, is_admin_authenticated, login_admin, logout_admin
from ctfarena.db import get_db
from ctfarena.services import ctf_service, runtime_settings
from ctfarena.services.competition import list_run_monitor
from ctfarena.services.ctfd import CTFdClient, CTFdSyncError
from ctfarena.utils import utc_now


bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if login_admin(
            request.form.get("username", ""),
            request.form.get("password", ""),
        ):
            flash("Admin session opened.", "success")
            next_url = request.args.get("next") or url_for("admin.dashboard")
            return redirect(next_url)
        flash("Invalid admin credentials.", "error")
    return render_template("frontend_admin/login.html")


@bp.post("/logout")
def logout():
    logout_admin()
    flash("Admin session closed.", "success")
    return redirect(url_for("frontend.index"))


@bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    ctfs = ctf_service.list_ctfs(db)
    models = ctf_service.list_models(db)
    account_map = {
        ctf["id"]: ctf_service.list_ctf_accounts(db, ctf["id"])
        for ctf in ctfs
    }
    run_monitor = {
        ctf["id"]: list_run_monitor(db, ctf["id"])
        for ctf in ctfs
    }
    settings = runtime_settings.get_all()
    masked_settings = {
        key: runtime_settings.masked(value)
        for key, value in settings.items()
        if key in runtime_settings.SECRET_KEYS
    }
    return render_template(
        "frontend_admin/dashboard.html",
        ctfs=ctfs,
        models=models,
        account_map=account_map,
        run_monitor=run_monitor,
        runtime_settings=settings,
        masked_settings=masked_settings,
        active_ctf=ctf_service.get_active_ctf(db),
        admin_logged_in=is_admin_authenticated(),
    )


@bp.post("/settings")
@admin_required
def update_settings():
    values = {
        "solver_image": request.form.get("solver_image", "").strip(),
        "solver_network": request.form.get("solver_network", "").strip() or "bridge",
        "solver_max_turns": request.form.get("solver_max_turns", "").strip() or "8",
        "solver_command_timeout_seconds": request.form.get(
            "solver_command_timeout_seconds",
            "",
        ).strip()
        or "20",
        "solver_llm_timeout_seconds": request.form.get("solver_llm_timeout_seconds", "").strip()
        or "90",
        "solver_extra_env": request.form.get("solver_extra_env", "").strip(),
    }
    for key in runtime_settings.SECRET_KEYS:
        posted = request.form.get(key, "")
        values[key] = posted.strip() if posted.strip() else "__KEEP__"
    runtime_settings.update(values)
    flash("Runtime settings saved.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/models/<int:model_id>")
@admin_required
def update_model(model_id: int):
    db = get_db()
    updated_at = utc_now()
    db.execute(
        """
        UPDATE model_profiles
        SET
            display_name = ?,
            provider = ?,
            model_name = ?,
            rate_key = ?,
            color = ?,
            reasoning_effort = ?,
            temperature = ?,
            enabled = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            request.form.get("display_name", "").strip(),
            request.form.get("provider", "").strip(),
            request.form.get("model_name", "").strip(),
            request.form.get("rate_key", "").strip(),
            request.form.get("color", "").strip() or "#0b7285",
            request.form.get("reasoning_effort", "").strip() or "high",
            request.form.get("temperature", type=float) or 0.2,
            1 if request.form.get("enabled") == "1" else 0,
            updated_at,
            model_id,
        ),
    )
    db.commit()
    flash("Model profile saved.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs")
@admin_required
def create_ctf():
    db = get_db()
    payload = {
        "title": request.form.get("title", "").strip(),
        "ctfd_url": request.form.get("ctfd_url", "").strip(),
        "ctfd_token": request.form.get("ctfd_token", "").strip(),
        "ctfd_auth_type": request.form.get("ctfd_auth_type", "token").strip(),
        "sandbox_digest": request.form.get("sandbox_digest", "").strip(),
        "flag_regex": request.form.get("flag_regex", r"flag\{.*?\}").strip(),
        "budget": {
            "wall_seconds": request.form.get("budget_wall_seconds", type=int)
            or current_app.config["DEFAULT_CTF_BUDGET"]["wall_seconds"],
            "input_tokens": request.form.get("budget_input_tokens", type=int)
            or current_app.config["DEFAULT_CTF_BUDGET"]["input_tokens"],
            "output_tokens": request.form.get("budget_output_tokens", type=int)
            or current_app.config["DEFAULT_CTF_BUDGET"]["output_tokens"],
            "usd": request.form.get("budget_usd", type=float)
            or current_app.config["DEFAULT_CTF_BUDGET"]["usd"],
            "flag_attempts": request.form.get("budget_flag_attempts", type=int)
            or current_app.config["DEFAULT_CTF_BUDGET"]["flag_attempts"],
        },
    }

    if not payload["title"] or not payload["ctfd_url"]:
        flash("Title and CTFd URL are required.", "error")
        return redirect(url_for("admin.dashboard"))

    ctf_id = ctf_service.create_ctf(db, payload)
    flash(f"Created CTF #{ctf_id}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/activate")
@admin_required
def activate_ctf(ctf_id: int):
    db = get_db()
    ctf_service.activate_ctf(db, ctf_id)
    flash("Active weekly CTF updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/sync")
@admin_required
def sync_ctf(ctf_id: int):
    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        flash("Unknown CTF.", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        client = CTFdClient(
            base_url=ctf["ctfd_url"],
            auth_value=ctf["ctfd_token"],
            auth_type=ctf["ctfd_auth_type"],
            timeout=current_app.config["REQUEST_TIMEOUT_SECONDS"],
        )
        challenges = client.fetch_challenges()
    except CTFdSyncError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    ctf_service.upsert_challenges(db, ctf_id=ctf_id, challenges=challenges)
    flash(f"Synced {len(challenges)} challenges from CTFd.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/accounts/<int:model_id>")
@admin_required
def upsert_account(ctf_id: int, model_id: int):
    db = get_db()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    team_name = request.form.get("team_name", "").strip()
    notes = request.form.get("notes", "").strip()

    if not username or not password:
        flash("Username and password are required for model accounts.", "error")
        return redirect(url_for("admin.dashboard"))

    ctf_service.upsert_ctf_account(
        db,
        ctf_id=ctf_id,
        model_id=model_id,
        username=username,
        password=password,
        team_name=team_name,
        notes=notes,
    )
    flash("CTF account saved.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/start")
@admin_required
def start_competition(ctf_id: int):
    try:
        manager = current_app.extensions["competition_manager"]
        manager.start_ctf(ctf_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    flash("Competition started across four models.", "success")
    return redirect(url_for("admin.dashboard"))
