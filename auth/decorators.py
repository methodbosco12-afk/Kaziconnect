from functools import wraps
from flask import session, redirect, url_for
from models import User


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("auth.admin_login"))

        user = User.query.get(session.get("user_id"))
        if not user or user.role != "admin":
            session.clear()
            return redirect(url_for("auth.admin_login"))

        return f(*args, **kwargs)
    return wrapper


def fundi_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "fundi":
            return redirect(url_for("auth.fundi_login"))
        return f(*args, **kwargs)
    return wrapper


def contractor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "contractor":
            return redirect(url_for("auth.contractor_login"))
        return f(*args, **kwargs)
    return wrapper