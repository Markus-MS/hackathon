from __future__ import annotations

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from ctfarena.auth import admin_required, is_admin_authenticated, login_admin, logout_admin
from ctfarena.db import get_db
from ctfarena.services import ctf_service, llm_catalog, pricing, runtime_settings
from ctfarena.services.competition import list_run_monitor
from ctfarena.services.ctfd import CTFdClient, CTFdSyncError
from ctfarena.telemetry import capture_admin_action, capture_exception
from ctfarena.utils import slugify, utc_now


bp = Blueprint("admin", __name__, url_prefix="/admin")
PROVIDER_OPTIONS = ("openai", "anthropic", "google", "deepseek", "openrouter")
SETTINGS_TABS = ("runtime", "providers", "agents", "observability")


def _settings_tab(value: str | None) -> str:
    tab = (value or "").strip().lower()
    return tab if tab in SETTINGS_TABS else SETTINGS_TABS[0]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if login_admin(
            request.form.get("username", ""),
            request.form.get("password", ""),
        ):
            capture_admin_action("admin.login", status="success")
            flash("Admin session opened.", "success")
            next_url = request.args.get("next") or url_for("admin.dashboard")
            return redirect(next_url)
        capture_admin_action("admin.login", status="failed")
        flash("Invalid admin credentials.", "error")
    return render_template("frontend_admin/login.html")


@bp.post("/logout")
def logout():
    logout_admin()
    capture_admin_action("admin.logout", status="success")
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
    rate_keys = sorted(pricing.get_rate_table())
    model_name_options = sorted({key.split(":", 1)[1] for key in rate_keys})
    active_settings_tab = _settings_tab(request.args.get("settings_tab"))
    return render_template(
        "frontend_admin/dashboard.html",
        ctfs=ctfs,
        models=models,
        provider_options=PROVIDER_OPTIONS,
        account_map=account_map,
        run_monitor=run_monitor,
        runtime_settings=settings,
        masked_settings=masked_settings,
        model_name_options=model_name_options,
        rate_key_options=rate_keys,
        active_ctf=ctf_service.get_active_ctf(db),
        active_settings_tab=active_settings_tab,
        admin_logged_in=is_admin_authenticated(),
    )


@bp.post("/settings")
@admin_required
def update_settings():
    active_settings_tab = _settings_tab(request.form.get("active_settings_tab"))
    solver_tool = request.form.get("solver_tool", "docker").strip()
    if solver_tool not in ("docker", "opencode"):
        solver_tool = "docker"
    log_level = request.form.get("log_level", "DEBUG").strip().upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        log_level = "DEBUG"
    values = {
        "log_level": log_level,
        "solver_tool": solver_tool,
        "solver_image": request.form.get("solver_image", "").strip(),
        "solver_network": request.form.get("solver_network", "").strip() or "bridge",
        "runner_max_parallel_runs": request.form.get(
            "runner_max_parallel_runs",
            "",
        ).strip()
        or "1",
        "solver_max_turns": request.form.get("solver_max_turns", "").strip() or "8",
        "solver_command_timeout_seconds": request.form.get(
            "solver_command_timeout_seconds",
            "",
        ).strip()
        or "20",
        "solver_llm_timeout_seconds": request.form.get("solver_llm_timeout_seconds", "").strip()
        or "90",
        "solver_grace_period_seconds": request.form.get("solver_grace_period_seconds", "").strip()
        or "300",
        "solver_extra_env": request.form.get("solver_extra_env", "").strip(),
        "opencode_config_dir": request.form.get("opencode_config_dir", "").strip(),
        "opencode_data_dir": request.form.get("opencode_data_dir", "").strip(),
        "opencode_extra_args": request.form.get("opencode_extra_args", "").strip(),
        "sentry_enabled": "1" if request.form.get("sentry_enabled") == "1" else "0",
        "sentry_browser_enabled": "1" if request.form.get("sentry_browser_enabled") == "1" else "0",
        "sentry_traces_sample_rate": request.form.get("sentry_traces_sample_rate", "").strip() or "0.95",
        "sentry_profiles_sample_rate": request.form.get("sentry_profiles_sample_rate", "").strip() or "0.5",
        "sentry_replays_session_sample_rate": request.form.get(
            "sentry_replays_session_sample_rate",
            "",
        ).strip()
        or "0.1",
        "sentry_replays_on_error_sample_rate": request.form.get(
            "sentry_replays_on_error_sample_rate",
            "",
        ).strip()
        or "1.0",
        "sentry_debug_mode_default": "1" if request.form.get("sentry_debug_mode_default") == "1" else "0",
        "openrouter_api_key": request.form.get("openrouter_api_key", "").strip(),
    }
    for key in runtime_settings.SECRET_KEYS:
        posted = request.form.get(key, "")
        values[key] = posted.strip() if posted.strip() else "__KEEP__"
    runtime_settings.update(values)
    runtime_settings.apply_log_level()
    capture_admin_action(
        "settings.update",
        status="success",
        payload={
            "sentry_enabled": values["sentry_enabled"],
            "sentry_browser_enabled": values["sentry_browser_enabled"],
            "log_level": values.get("log_level", "DEBUG"),
        },
    )
    flash("Runtime settings saved.", "success")
    return redirect(url_for("admin.dashboard", settings_tab=active_settings_tab))


@bp.post("/models/<int:model_id>")
@admin_required
def update_model(model_id: int):
    db = get_db()
    updated_at = utc_now()
    provider = request.form.get("provider", "").strip()
    model_name = request.form.get("model_name", "").strip()
    rate_key = request.form.get("rate_key", "").strip() or f"{provider}:{model_name}"
    temperature = request.form.get("temperature", type=float)
    provider_api_key = request.form.get("provider_api_key", "").strip()
    if provider_api_key == "__KEEP__":
        provider_api_key = ""
    if provider_api_key and not runtime_settings.set_provider_api_key(provider, provider_api_key):
        capture_admin_action("model.update", status="failed", payload={"model_id": model_id, "reason": "unsupported_provider"})
        flash("Unsupported provider for API key storage.", "error")
        return redirect(url_for("admin.dashboard"))
    if not _ensure_provider_rate(
        provider=provider,
        model_name=model_name,
        rate_key=rate_key,
        api_key=provider_api_key or runtime_settings.provider_api_key(provider),
    ):
        return redirect(url_for("admin.dashboard"))
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
            provider,
            model_name,
            rate_key,
            request.form.get("color", "").strip() or "#0b7285",
            request.form.get("reasoning_effort", "").strip() or "high",
            0.2 if temperature is None else temperature,
            1 if request.form.get("enabled") == "1" else 0,
            updated_at,
            model_id,
        ),
    )
    db.commit()
    capture_admin_action("model.update", status="success", payload={"model_id": model_id, "provider": provider})
    flash(
        "Model profile saved."
        + (" Provider API key saved." if provider_api_key else ""),
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@bp.post("/models/<int:model_id>/delete")
@admin_required
def delete_model(model_id: int):
    db = get_db()
    model = ctf_service.delete_model(db, model_id)
    if model is None:
        flash("Unknown model profile.", "error")
        return redirect(url_for("admin.dashboard"))

    flash(f"Removed model profile {model['display_name']}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/llm-models")
@admin_required
def list_llm_models():
    provider = request.form.get("provider", "").strip()
    api_key = request.form.get("api_key", "").strip() or runtime_settings.provider_api_key(provider)
    if not provider:
        return jsonify({"error": "Provider is required."}), 400
    if not api_key:
        return jsonify({"error": "Paste an API key or save one in Runtime Settings first."}), 400

    try:
        catalog = llm_catalog.list_model_catalog(
            provider,
            api_key,
            timeout=current_app.config["REQUEST_TIMEOUT_SECONDS"],
        )
    except llm_catalog.LLMCatalogError as exc:
        return jsonify({"error": str(exc)}), 400

    if provider == "openrouter":
        pricing.upsert_dynamic_rates(
            {
                f"{provider}:{str(item['id'])}": item["pricing"]
                for item in catalog
                if isinstance(item.get("pricing"), dict)
            }
        )

    models = [str(item["id"]) for item in catalog]
    rate_keys = pricing.get_rate_table()
    models = sorted(
        models,
        key=lambda model_name: (
            f"{provider}:{model_name}" not in rate_keys,
            model_name,
        ),
    )
    return jsonify({"models": models, "rate_keys": [f"{provider}:{model_name}" for model_name in models]})


@bp.post("/models")
@admin_required
def create_model():
    db = get_db()
    now = utc_now()
    provider = request.form.get("provider", "").strip()
    model_name = request.form.get("model_name", "").strip()
    display_name = request.form.get("display_name", "").strip()
    slug_root = slugify(request.form.get("slug", "").strip() or display_name or model_name)
    rate_key = request.form.get("rate_key", "").strip() or f"{provider}:{model_name}"
    provider_api_key = request.form.get("provider_api_key", "").strip()
    if provider_api_key == "__KEEP__":
        provider_api_key = ""

    if not display_name or not provider or not model_name:
        flash("Display name, provider, and model name are required.", "error")
        return redirect(url_for("admin.dashboard"))
    if not slug_root:
        flash("Model slug must include at least one letter or number.", "error")
        return redirect(url_for("admin.dashboard"))
    if provider_api_key and not runtime_settings.set_provider_api_key(provider, provider_api_key):
        flash("Unsupported provider for API key storage.", "error")
        return redirect(url_for("admin.dashboard"))
    if not _ensure_provider_rate(
        provider=provider,
        model_name=model_name,
        rate_key=rate_key,
        api_key=provider_api_key or runtime_settings.provider_api_key(provider),
    ):
        return redirect(url_for("admin.dashboard"))

    slug = slug_root
    suffix = 2
    while db.execute("SELECT 1 FROM model_profiles WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug_root}-{suffix}"
        suffix += 1

    temperature = request.form.get("temperature", type=float)
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.5, ?, ?, ?)
        """,
        (
            slug,
            display_name,
            provider,
            model_name,
            rate_key,
            request.form.get("color", "").strip() or "#0b7285",
            request.form.get("reasoning_effort", "").strip() or "high",
            0.2 if temperature is None else temperature,
            1 if request.form.get("enabled") == "1" else 0,
            now,
            now,
        ),
    )
    db.commit()
    flash(
        f"Added model profile {display_name}."
        + (" Provider API key saved." if provider_api_key else ""),
        "success",
    )
    return redirect(url_for("admin.dashboard"))


def _ensure_provider_rate(*, provider: str, model_name: str, rate_key: str, api_key: str) -> bool:
    provider = provider.strip().lower()
    if provider != "openrouter":
        return True

    canonical_rate_key = f"{provider}:{model_name}"
    rates = pricing.get_rate_table()
    if rate_key in rates or canonical_rate_key in rates:
        if rate_key != canonical_rate_key and canonical_rate_key in rates and rate_key not in rates:
            pricing.upsert_dynamic_rates({rate_key: rates[canonical_rate_key]})
        return True
    if not api_key:
        flash(
            "OpenRouter API key is required to load pricing for new OpenRouter models.",
            "error",
        )
        return False

    try:
        catalog = llm_catalog.list_model_catalog(
            provider,
            api_key,
            timeout=current_app.config["REQUEST_TIMEOUT_SECONDS"],
        )
    except llm_catalog.LLMCatalogError as exc:
        flash(str(exc), "error")
        return False

    pricing.upsert_dynamic_rates(
        {
            f"{provider}:{str(item['id'])}": item["pricing"]
            for item in catalog
            if isinstance(item.get("pricing"), dict)
        }
    )
    rates = pricing.get_rate_table()
    if rate_key != canonical_rate_key and canonical_rate_key in rates:
        pricing.upsert_dynamic_rates({rate_key: rates[canonical_rate_key]})
        rates = pricing.get_rate_table()
    if rate_key not in rates and canonical_rate_key not in rates:
        flash(f"OpenRouter did not return pricing for model {model_name}.", "error")
        return False
    return True


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
        capture_admin_action("ctf.create", status="failed", payload={"reason": "missing_required"})
        flash("Title and CTFd URL are required.", "error")
        return redirect(url_for("admin.dashboard"))

    ctf_id = ctf_service.create_ctf(db, payload)
    capture_admin_action("ctf.create", status="success", payload={"ctf_id": ctf_id, "title": payload["title"]})
    flash(f"Created CTF #{ctf_id}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/activate")
@admin_required
def activate_ctf(ctf_id: int):
    db = get_db()
    ctf_service.activate_ctf(db, ctf_id)
    capture_admin_action("ctf.activate", status="success", payload={"ctf_id": ctf_id})
    flash("Active weekly CTF updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/sync")
@admin_required
def sync_ctf(ctf_id: int):
    db = get_db()
    ctf = ctf_service.get_ctf(db, ctf_id)
    if ctf is None:
        capture_admin_action("ctf.sync", status="failed", payload={"ctf_id": ctf_id, "reason": "unknown_ctf"})
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
        capture_exception(exc, tags={"action": "ctf.sync", "ctf_id": ctf_id})
        capture_admin_action("ctf.sync", status="failed", payload={"ctf_id": ctf_id})
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    ctf_service.upsert_challenges(db, ctf_id=ctf_id, challenges=challenges)
    capture_admin_action("ctf.sync", status="success", payload={"ctf_id": ctf_id, "challenge_count": len(challenges)})
    flash(f"Synced {len(challenges)} challenges from CTFd.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/ctfs/<int:ctf_id>/accounts/<int:model_id>")
@admin_required
def upsert_account(ctf_id: int, model_id: int):
    db = get_db()
    existing = ctf_service.get_ctf_account(db, ctf_id, model_id)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    api_token = request.form.get("api_token", "").strip()
    team_name = request.form.get("team_name", "").strip()
    notes = request.form.get("notes", "").strip()

    if password == "__KEEP__":
        password = ""
    if api_token == "__KEEP__":
        api_token = ""

    if existing is not None:
        username = username or existing["username"]
        password = password or existing["password"]
        api_token = api_token or existing["api_token"]

    if not api_token:
        capture_admin_action(
            "ctf.account.upsert",
            status="failed",
            payload={"ctf_id": ctf_id, "model_id": model_id, "reason": "missing_api_token"},
        )
        flash(
            "Add a per-model CTFd API token. Username and password are only notes for the solver.",
            "error",
        )
        return redirect(url_for("admin.dashboard"))

    ctf_service.upsert_ctf_account(
        db,
        ctf_id=ctf_id,
        model_id=model_id,
        username=username,
        password=password,
        api_token=api_token,
        team_name=team_name,
        notes=notes,
    )
    capture_admin_action("ctf.account.upsert", status="success", payload={"ctf_id": ctf_id, "model_id": model_id})
    flash("CTF account saved.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/competition-runs/<int:competition_run_id>/delete")
@admin_required
def delete_competition_run(competition_run_id: int):
    db = get_db()
    row = db.execute(
        "SELECT id FROM competition_runs WHERE id = ?", (competition_run_id,)
    ).fetchone()
    if row is None:
        flash("Competition run not found.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("DELETE FROM competition_runs WHERE id = ?", (competition_run_id,))
    db.commit()
    capture_admin_action(
        "competition_run.delete",
        status="success",
        payload={"competition_run_id": competition_run_id},
    )
    flash(f"Deleted competition run #{competition_run_id}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/challenge-runs/<int:challenge_run_id>/rerun")
@admin_required
def rerun_challenge_run(challenge_run_id: int):
    try:
        manager = current_app.extensions["competition_manager"]
        manager.rerun_challenge_run(challenge_run_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        capture_exception(exc, tags={"action": "challenge_run.rerun", "challenge_run_id": challenge_run_id})
        return jsonify({"error": str(exc)}), 500
    capture_admin_action("challenge_run.rerun", status="success", payload={"challenge_run_id": challenge_run_id})
    return jsonify({"ok": True})


@bp.post("/ctfs/<int:ctf_id>/start")
@admin_required
def start_competition(ctf_id: int):
    debug_mode = request.form.get("sentry_debug_mode") == "1"
    try:
        manager = current_app.extensions["competition_manager"]
        run_ids = manager.start_ctf(ctf_id, sentry_debug=debug_mode)
    except ValueError as exc:
        capture_admin_action(
            "competition.start",
            status="failed",
            payload={"ctf_id": ctf_id, "debug_mode": debug_mode},
        )
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    run_count = len(run_ids)
    noun = "model" if run_count == 1 else "models"
    capture_admin_action(
        "competition.start",
        status="success",
        payload={"ctf_id": ctf_id, "run_count": run_count, "debug_mode": debug_mode},
    )
    flash(f"Competition started for {run_count} {noun}.", "success")
    return redirect(url_for("admin.dashboard"))
