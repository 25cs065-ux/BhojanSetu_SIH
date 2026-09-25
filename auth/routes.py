"""
auth/routes.py
==============
Authentication Blueprint for BhojanSetu.

Routes
------
GET  /auth/login          → login page
POST /auth/login          → authenticate user
GET  /auth/signup         → signup page
POST /auth/signup         → register user + generate OTP
GET  /auth/verify-otp     → OTP entry page
POST /auth/verify-otp     → verify OTP and activate session
GET  /auth/logout         → destroy session
GET  /auth/resend-otp     → regenerate OTP
"""

from __future__ import annotations

from flask import (
    Blueprint, flash, redirect, render_template,
    request, session, url_for,
)

from auth.utils import (
    create_user,
    generate_otp,
    get_user_by_email,
    mark_verified,
    verify_credentials,
    verify_otp as _verify_otp,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROLE_DASHBOARD = {
    "kitchen": "dashboard_kitchen",
    "ngo":     "dashboard_ngo",
    "admin":   "dashboard_admin",
}


def _redirect_dashboard():
    role = session.get("role", "kitchen")
    endpoint = _ROLE_DASHBOARD.get(role, "dashboard_kitchen")
    return redirect(url_for(endpoint))


def _login_required(fn):
    """Simple decorator — redirect to login if session missing."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return _redirect_dashboard()

    if request.method == "POST":
        email    = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        user = verify_credentials(email, password)
        if user is None:
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        # Populate session
        session["user_id"]    = user["user_id"]
        session["user_name"]  = user.get("full_name", email)
        session["role"]       = user.get("role", "kitchen")
        session["institution"] = user.get("institution", "")
        session["email"]      = user.get("email", email)

        return _redirect_dashboard()

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return _redirect_dashboard()

    if request.method == "POST":
        full_name        = (request.form.get("full_name") or "").strip()
        role             = (request.form.get("role") or "").strip().lower()
        institution      = (request.form.get("institution") or "").strip()
        email            = (request.form.get("email") or "").strip().lower()
        password         = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        # Basic validation
        if not full_name:
            flash("Full name is required.", "error")
            return render_template("signup.html")
        if role not in ("kitchen", "ngo"):
            flash("Please select a valid role.", "error")
            return render_template("signup.html")
        if not institution:
            flash("Institution / organisation name is required.", "error")
            return render_template("signup.html")
        if not email or "@" not in email:
            flash("Enter a valid email address.", "error")
            return render_template("signup.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        try:
            create_user(
                email=email,
                password=password,
                full_name=full_name,
                role=role,
                institution=institution,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("signup.html")

        # Store OTP context in session and generate OTP
        otp = generate_otp(email)
        session["pending_email"] = email
        # In production, email the OTP.  For demo: show it via flash.
        flash(
            f"Account created! Your OTP is: {otp}  (In production this would be emailed.)",
            "success",
        )
        return redirect(url_for("auth.verify_otp"))

    return render_template("signup.html")


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    pending_email = session.get("pending_email")
    if not pending_email:
        flash("No pending verification. Please sign up first.", "error")
        return redirect(url_for("auth.signup"))

    if request.method == "POST":
        otp = (request.form.get("otp") or "").strip()
        if not otp or not otp.isdigit() or len(otp) != 6:
            flash("Enter a valid 6-digit OTP.", "error")
            return render_template("otp_verify.html")

        if not _verify_otp(pending_email, otp):
            flash("Invalid or expired OTP. Please try again.", "error")
            return render_template("otp_verify.html")

        # Mark user verified and log them in
        mark_verified(pending_email)
        user = get_user_by_email(pending_email)
        session.pop("pending_email", None)

        if user:
            session["user_id"]     = user["user_id"]
            session["user_name"]   = user.get("full_name", pending_email)
            session["role"]        = user.get("role", "kitchen")
            session["institution"] = user.get("institution", "")
            session["email"]       = user.get("email", pending_email)
            flash("Email verified! Welcome to BhojanSetu.", "success")
            return _redirect_dashboard()
        else:
            flash("Verification succeeded but user record not found. Please log in.", "info")
            return redirect(url_for("auth.login"))

    return render_template("otp_verify.html")


# ---------------------------------------------------------------------------
# Resend OTP
# ---------------------------------------------------------------------------

@auth_bp.route("/resend-otp")
def resend_otp():
    pending_email = session.get("pending_email")
    if not pending_email:
        flash("No pending verification.", "error")
        return redirect(url_for("auth.signup"))

    otp = generate_otp(pending_email)
    flash(f"New OTP generated: {otp}  (In production this would be emailed.)", "success")
    return redirect(url_for("auth.verify_otp"))


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
