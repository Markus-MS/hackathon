from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager, nullcontext
from typing import Any

import sentry_sdk
from flask import Flask, current_app, g, has_app_context, has_request_context, request, session
from sentry_sdk import metrics
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from ctfarena.db import get_setting
from ctfarena.services import runtime_settings


FLAG_PATTERN = re.compile(r"flag\{.*?\}", re.IGNORECASE)
TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]
LONG_HEX_PATTERN = re.compile(r"\b[a-f0-9]{24,}\b", re.IGNORECASE)
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "ctfd_token",
    "password",
    "prompt",
    "prompt_template",
    "solver_output",
    "x-api-key",
}
SCRUB_EXCERPT_KEYS = {
    "connection_info",
    "description",
    "details",
    "error_message",
    "stderr",
    "stdout",
    "transcript_excerpt",
}
_SENTRY_INITIALIZED = False


def _setting_value(key: str, default: str = "") -> str:
    if not has_app_context():
        return default
    try:
        return get_setting(key, default) or default
    except Exception:
        return default


def sentry_enabled() -> bool:
    if _SENTRY_INITIALIZED and not has_app_context():
        return True
    if not has_app_context():
        return False
    if not current_app.config.get("SENTRY_DSN"):
        return False
    return _setting_value("sentry_enabled", runtime_settings.DEFAULT_SETTINGS["sentry_enabled"]).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def sentry_debug_mode_active() -> bool:
    if has_request_context():
        if request.headers.get("X-CTFArena-Sentry-Debug", "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if request.args.get("sentry_debug", "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    if has_app_context():
        return runtime_settings.enabled("sentry_debug_mode_default")
    return False


def _base_trace_sample_rate() -> float:
    if not has_app_context():
        return 0.95
    return runtime_settings.sample_rate("sentry_traces_sample_rate")


def _truncate(value: str, *, limit: int = 240) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated:{len(value) - limit}]"


def _scrub_string(value: str, *, redact_long_text: bool = False) -> str:
    cleaned = FLAG_PATTERN.sub("[redacted-flag]", value)
    cleaned = LONG_HEX_PATTERN.sub("[redacted-token]", cleaned)
    for pattern in TOKEN_PATTERNS:
        cleaned = pattern.sub("[redacted-token]", cleaned)
    if redact_long_text:
        cleaned = _truncate(cleaned, limit=120)
    return cleaned


def _scrub_value(value: Any, *, key: str | None = None) -> Any:
    normalized_key = (key or "").lower()
    if normalized_key in SENSITIVE_KEYS or normalized_key.endswith(
        ("_token", "_secret", "_password", "_key")
    ):
        return "[redacted]"
    if isinstance(value, str):
        return _scrub_string(value, redact_long_text=normalized_key in SCRUB_EXCERPT_KEYS)
    if isinstance(value, list):
        return [_scrub_value(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, key=key) for item in value)
    if isinstance(value, Mapping):
        cleaned: MutableMapping[str, Any] = {}
        for item_key, item in value.items():
            cleaned[str(item_key)] = _scrub_value(item, key=str(item_key))
        return cleaned
    return value


def scrub_mapping(payload: Mapping[str, object]) -> dict[str, object]:
    return dict(_scrub_value(dict(payload)))


def _before_send(event: dict[str, Any], _: dict[str, Any]) -> dict[str, Any] | None:
    if not sentry_enabled():
        return None
    return _scrub_value(event)


def _traces_sampler(sampling_context: dict[str, Any]) -> float:
    if not sentry_enabled():
        return 0.0
    if sampling_context.get("parent_sampled") is not None:
        return float(bool(sampling_context["parent_sampled"]))

    transaction_context = sampling_context.get("transaction_context") or {}
    name = str(transaction_context.get("name") or "")
    if name in {"GET /healthz", "GET /health", "frontend.healthz"}:
        return 0.0
    return _base_trace_sample_rate()


def _request_tags() -> dict[str, object]:
    if not has_request_context():
        return {}
    return {
        "request_id": request.headers.get("X-Request-Id", ""),
        "route": request.path,
        "method": request.method,
        "endpoint": request.endpoint or "",
        "blueprint": request.blueprint or "",
        "admin_authenticated": bool(session.get("is_admin")),
        "debug_mode": sentry_debug_mode_active(),
    }


def _attach_request_scope() -> None:
    if not sentry_enabled() or not has_request_context():
        return
    g.sentry_debug_mode = sentry_debug_mode_active()
    scope = sentry_sdk.get_current_scope()
    for key, value in _request_tags().items():
        scope.set_tag(key, value)
    scope.set_context(
        "request_meta",
        scrub_mapping(
            {
                "args": dict(request.args),
                "path": request.path,
                "method": request.method,
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            }
        ),
    )
    if session.get("is_admin"):
        scope.set_user(
            {
                "id": "admin-session",
                "username": session.get("admin_username", "admin"),
                "segment": "admin",
            }
        )
    sentry_sdk.add_breadcrumb(
        category="http.request",
        type="http",
        level="info",
        message=f"{request.method} {request.path}",
        data=scrub_mapping({"args": dict(request.args), "endpoint": request.endpoint or ""}),
    )


def _attach_response_scope(response) -> object:
    if not sentry_enabled() or not has_request_context():
        return response
    scope = sentry_sdk.get_current_scope()
    scope.set_tag("http_status", response.status_code)
    if response.status_code >= 400:
        sentry_sdk.add_breadcrumb(
            category="http.response",
            type="http",
            level="warning" if response.status_code < 500 else "error",
            message=f"{request.method} {request.path} -> {response.status_code}",
        )
    return response


def browser_config(*, release: str, environment: str) -> dict[str, object]:
    browser_dsn = _setting_value("sentry_browser_dsn", "")
    enabled = (
        sentry_enabled()
        and runtime_settings.enabled("sentry_browser_enabled")
        and bool(browser_dsn)
    )
    return {
        "enabled": enabled,
        "dsn": browser_dsn,
        "environment": environment,
        "release": release,
        "traces_sample_rate": runtime_settings.sample_rate("sentry_traces_sample_rate"),
        "replays_session_sample_rate": runtime_settings.sample_rate("sentry_replays_session_sample_rate"),
        "replays_on_error_sample_rate": runtime_settings.sample_rate("sentry_replays_on_error_sample_rate"),
        "debug_mode_default": runtime_settings.enabled("sentry_debug_mode_default"),
    }


def init_sentry(*, app: Flask, component: str, release: str, environment: str) -> None:
    global _SENTRY_INITIALIZED

    app.extensions["sentry_release"] = release
    app.extensions["sentry_environment"] = environment

    dsn = str(app.config.get("SENTRY_DSN") or "")
    if _SENTRY_INITIALIZED or not dsn:
        return

    with app.app_context():
        profiles_sample_rate = runtime_settings.sample_rate("sentry_profiles_sample_rate")

    sentry_sdk.init(
        dsn=dsn,
        release=release,
        environment=environment,
        integrations=[
            FlaskIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=False,
        enable_logs=True,
        traces_sampler=_traces_sampler,
        profiles_sample_rate=profiles_sample_rate,
        attach_stacktrace=True,
        before_send=_before_send,
    )
    sentry_sdk.set_tag("component", component)
    _SENTRY_INITIALIZED = True

    @app.before_request
    def _sentry_before_request() -> None:
        _attach_request_scope()

    @app.after_request
    def _sentry_after_request(response):
        return _attach_response_scope(response)


def template_config() -> dict[str, object]:
    if not has_app_context():
        return {"enabled": False}
    return browser_config(
        release=str(current_release()),
        environment=str(current_environment()),
    )


def current_release() -> str:
    if not has_app_context():
        return ""
    return str(current_app.extensions.get("sentry_release", ""))


def current_environment() -> str:
    if not has_app_context():
        return ""
    return str(current_app.extensions.get("sentry_environment", ""))


def add_breadcrumb(*, category: str, message: str, level: str = "info", data: Mapping[str, object] | None = None) -> None:
    if not sentry_enabled():
        return
    sentry_sdk.add_breadcrumb(
        category=category,
        message=message,
        level=level,
        data=scrub_mapping(data or {}),
    )


def set_tags(tags: Mapping[str, object]) -> None:
    if not sentry_enabled():
        return
    scope = sentry_sdk.get_current_scope()
    for key, value in tags.items():
        scope.set_tag(key, value)


def set_context(name: str, payload: Mapping[str, object]) -> None:
    if not sentry_enabled():
        return
    sentry_sdk.get_current_scope().set_context(name, scrub_mapping(payload))


def capture_message(message: str, *, level: str = "info", tags: Mapping[str, object] | None = None, context: Mapping[str, object] | None = None) -> str | None:
    if not sentry_enabled():
        return None
    with sentry_sdk.new_scope() as scope:
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)
        if context:
            scope.set_context("details", scrub_mapping(context))
        return sentry_sdk.capture_message(_scrub_string(message), level=level)


def capture_exception(exc: BaseException, *, tags: Mapping[str, object] | None = None, context: Mapping[str, object] | None = None) -> str | None:
    if not sentry_enabled():
        return None
    with sentry_sdk.new_scope() as scope:
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)
        if context:
            scope.set_context("details", scrub_mapping(context))
        return sentry_sdk.capture_exception(exc)


@contextmanager
def start_span(
    *,
    op: str,
    name: str,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[object]:
    if not sentry_enabled():
        with nullcontext(None) as span:
            yield span
        return
    span_attributes = scrub_mapping(attributes or {})
    with sentry_sdk.start_span(op=op, name=name) as span:
        for key, value in span_attributes.items():
            span.set_data(key, value)
        yield span


@contextmanager
def start_transaction(
    *,
    op: str,
    name: str,
    attributes: Mapping[str, object] | None = None,
    sampled: bool | None = None,
) -> Iterator[object]:
    if not sentry_enabled():
        with nullcontext(None) as transaction:
            yield transaction
        return
    transaction_attributes = scrub_mapping(attributes or {})
    with sentry_sdk.start_transaction(
        op=op,
        name=name,
        sampled=sampled,
    ) as transaction:
        for key, value in transaction_attributes.items():
            transaction.set_data(key, value)
        yield transaction


def metric_count(name: str, value: int = 1, *, tags: Mapping[str, str] | None = None) -> None:
    if not sentry_enabled():
        return
    metrics.count(name, value, attributes=scrub_mapping(tags or {}))


def metric_gauge(name: str, value: int | float, *, tags: Mapping[str, str] | None = None) -> None:
    if not sentry_enabled():
        return
    metrics.gauge(name, value, attributes=scrub_mapping(tags or {}))


def metric_distribution(name: str, value: int | float, *, tags: Mapping[str, str] | None = None) -> None:
    if not sentry_enabled():
        return
    metrics.distribution(name, value, attributes=scrub_mapping(tags or {}))


def capture_admin_action(action: str, *, status: str, payload: Mapping[str, object] | None = None) -> None:
    details = {"action": action, "status": status, **(payload or {})}
    add_breadcrumb(category="admin.action", message=f"{action} [{status}]", data=details)
    metric_count("ctfarena.admin_action", 1, tags={"action": action, "status": status})
    if status != "success":
        capture_message(
            f"Admin action {action} ended as {status}",
            level="warning",
            tags={"action": action, "status": status},
            context=details,
        )
