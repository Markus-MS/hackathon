#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "flask",
#   "openfeature-sdk",
#   "requests",
#   "sentry-sdk",
# ]
# ///

import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import requests
import sentry_sdk
from flask import Flask, Response, has_request_context, jsonify, request
from openfeature import api as openfeature_api
from openfeature.provider import AbstractProvider, FlagResolutionDetails, Metadata
from sentry_sdk import metrics
from sentry_sdk.crons.decorator import monitor
from sentry_sdk.integrations.openfeature import OpenFeatureIntegration


DSN = os.environ.get(
    "SENTRY_DSN",
    "https://f271196a290a90a866d33acb56d25eed@o4511239870939136.ingest.de.sentry.io/4511240223653968",
)
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", "hackathon")
RELEASE = os.environ.get("SENTRY_RELEASE", "sentry-flask-starter@1.0.0")
SERVER_NAME = os.environ.get("SENTRY_SERVER_NAME", "sentry-flask-starter")


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.frontend import frontend_bp


class StaticFlagProvider(AbstractProvider):
    def get_metadata(self) -> Metadata:
        return Metadata(name="static-hackathon-provider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context=None,
    ) -> FlagResolutionDetails[bool]:
        flags = {
            "new-checkout": True,
            "beta-dashboard": True,
            "danger-mode": False,
        }
        return FlagResolutionDetails(
            value=flags.get(flag_key, default_value),
            reason="STATIC",
            variant="enabled" if flags.get(flag_key, default_value) else "disabled",
        )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context=None,
    ) -> FlagResolutionDetails[str]:
        values = {
            "theme": "sentry-red",
            "checkout-flow": "fast-lane",
        }
        return FlagResolutionDetails(
            value=values.get(flag_key, default_value),
            reason="STATIC",
            variant=flag_key,
        )

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context=None,
    ) -> FlagResolutionDetails[int]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context=None,
    ) -> FlagResolutionDetails[float]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Any,
        evaluation_context=None,
    ) -> FlagResolutionDetails[Any]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)


def traces_sampler(sampling_context: dict[str, Any]) -> float:
    path = request.path if has_request_context() else None
    if path == "/health":
        return 0.0
    return 1.0


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("tags", {})
    event["tags"]["demo"] = "sentry-flask-starter"
    event["tags"]["hackathon"] = "true"
    return event


openfeature_api.set_provider(StaticFlagProvider())

sentry_sdk.init(
    dsn=DSN,
    environment=ENVIRONMENT,
    release=RELEASE,
    server_name=SERVER_NAME,
    send_default_pii=True,
    enable_logs=True,
    traces_sampler=traces_sampler,
    profile_session_sample_rate=1.0,
    profile_lifecycle="trace",
    attach_stacktrace=True,
    integrations=[OpenFeatureIntegration()],
    before_send=before_send,
)


app = Flask(__name__)
app.register_blueprint(frontend_bp)


def base_url() -> str:
    return f"http://{HOST}:{PORT}"


def annotate_request(scope) -> None:
    user_id = request.args.get("user", "hackathon-user")
    tier = request.args.get("tier", "pro")
    scope.set_user(
        {
            "id": user_id,
            "username": user_id,
            "email": f"{user_id}@example.com",
            "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
            "segment": tier,
        }
    )
    scope.set_tag("route", request.path)
    scope.set_tag("hackathon", "true")
    scope.set_tag("request_id", request.headers.get("X-Request-Id", "demo-request"))
    scope.set_context(
        "feature_flags",
        {
            "new-checkout": True,
            "beta-dashboard": True,
            "danger-mode": False,
        },
    )
    scope.set_context(
        "request_demo",
        {
            "method": request.method,
            "path": request.path,
            "args": dict(request.args),
        },
    )
    scope.set_extra("query_args", dict(request.args))
    scope.add_attachment(
        bytes=f"route={request.path}\nargs={dict(request.args)}\n".encode(),
        filename="request.txt",
        content_type="text/plain",
    )


def instrument_demo(name: str) -> None:
    with sentry_sdk.start_span(op="demo.step", name=f"{name}.db"):
        time.sleep(0.03)
    with sentry_sdk.start_span(op="demo.step", name=f"{name}.compute"):
        time.sleep(0.02)


@monitor(monitor_slug="hackathon-demo-checkin")
def run_monitored_job() -> dict[str, Any]:
    with sentry_sdk.start_span(op="job.fetch", name="load inputs"):
        time.sleep(0.02)
    with sentry_sdk.start_span(op="job.process", name="process inputs"):
        time.sleep(0.02)
    return {"monitor": "sent", "slug": "hackathon-demo-checkin"}


@app.before_request
def add_breadcrumb() -> None:
    sentry_sdk.add_breadcrumb(
        category="http",
        type="http",
        level="info",
        message=f"{request.method} {request.path}",
        data={"args": dict(request.args)},
    )


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status=204)


@app.get("/api")
def api_index():
    return jsonify(
        service="sentry-flask-starter",
        environment=ENVIRONMENT,
        release=RELEASE,
        endpoints={
            "/": "interactive Sentry demo homepage",
            "/health": "low-noise health route, excluded from tracing",
            "/message": "capture a manual Sentry message with request context",
            "/handled": "capture a handled exception",
            "/debug-sentry": "raise an unhandled exception",
            "/logs": "send structured logs to Sentry",
            "/metrics": "emit count, gauge, and distribution metrics",
            "/trace": "custom transaction, spans, and outbound HTTP request",
            "/feedback": "manual user-facing feedback event",
            "/cron": "send a cron monitor check-in",
            "/feature-flags": "evaluate OpenFeature flags with Sentry integration",
            "/smoke": "trigger several useful signals in one request",
        },
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/message")
def message():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_level("warning")
        event_id = sentry_sdk.capture_message("Hackathon test message from Flask", level="warning")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="message", event_id=event_id)


@app.get("/handled")
def handled():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_tag("error_kind", "handled")
        try:
            raise RuntimeError("Handled exception for Sentry demo")
        except RuntimeError as exc:
            event_id = sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="handled_exception", event_id=event_id)


@app.get("/debug-sentry")
def debug_sentry():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_tag("error_kind", "unhandled")
        instrument_demo("debug-sentry")
        1 / 0


@app.get("/logs")
def logs():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        sentry_sdk.logger.info("Sentry logger info", route=request.path)
        sentry_sdk.logger.warning("Sentry logger warning", route=request.path)
        sentry_sdk.logger.error("Sentry logger error", route=request.path)
        logger.info("Python logging info for Sentry")
        logger.warning("Python logging warning for Sentry")
        logger.error("Python logging error for Sentry")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="logs")


@app.get("/metrics")
def emit_metrics():
    amount = round(random.uniform(25, 250), 2)
    queue_depth = random.randint(1, 50)
    user_id = request.args.get("user", "hackathon-user")
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        metrics.count("checkout.started", 1, attributes={"env": ENVIRONMENT})
        metrics.count("checkout.failed", 1, attributes={"env": ENVIRONMENT, "flow": "fast-lane"})
        metrics.gauge("queue.depth", queue_depth, attributes={"env": ENVIRONMENT})
        metrics.distribution("cart.amount_usd", amount, attributes={"env": ENVIRONMENT})
        metrics.distribution("users.name_length", len(user_id), attributes={"env": ENVIRONMENT})
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="metrics", amount=amount, queue_depth=queue_depth)


@app.get("/trace")
def trace():
    with sentry_sdk.start_transaction(name="hackathon.trace", op="http.server") as transaction:
        with sentry_sdk.new_scope() as scope:
            annotate_request(scope)
            instrument_demo("trace")
            response = requests.get(f"{base_url()}/health", timeout=3)
            transaction.set_tag("health_status", response.status_code)
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="trace", downstream_status=response.status_code)


@app.get("/feedback")
def feedback():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        event_id = sentry_sdk.capture_message("User feedback submitted", level="info")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(
        status="captured",
        type="feedback_seed",
        event_id=event_id,
        note="Use this event_id with the Sentry user feedback UI/API.",
    )


@app.get("/cron")
def cron():
    payload = run_monitored_job()
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="cron", **payload)


@app.get("/feature-flags")
def feature_flags():
    client = openfeature_api.get_client()
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        new_checkout = client.get_boolean_value("new-checkout", False)
        beta_dashboard = client.get_boolean_value("beta-dashboard", False)
        theme = client.get_string_value("theme", "default")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(
        status="captured",
        type="feature_flags",
        flags={
            "new-checkout": new_checkout,
            "beta-dashboard": beta_dashboard,
            "theme": theme,
        },
    )


@app.get("/smoke")
def smoke():
    results = {
        "message": message().json,
        "handled": handled().json,
        "logs": logs().json,
        "metrics": emit_metrics().json,
        "trace": trace().json,
        "feature_flags": feature_flags().json,
        "cron": cron().json,
    }
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="smoke", results=results)


def main():
    logger.info("Starting Sentry Flask demo on http://%s:%s", HOST, PORT)
    logger.info("Sentry environment=%s release=%s server_name=%s", ENVIRONMENT, RELEASE, SERVER_NAME)
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
