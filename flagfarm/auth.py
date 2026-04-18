from __future__ import annotations

from functools import wraps

from flask import current_app, redirect, request, session, url_for


def login_admin(username: str, password: str) -> bool:
    if (
        username == current_app.config["ADMIN_USERNAME"]
        and password == current_app.config["ADMIN_PASSWORD"]
    ):
        session["is_admin"] = True
        session["admin_username"] = username
        return True
    return False


def logout_admin() -> None:
    session.pop("is_admin", None)
    session.pop("admin_username", None)


def is_admin_authenticated() -> bool:
    return bool(session.get("is_admin"))


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not is_admin_authenticated():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view
