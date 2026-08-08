"""HTTP API for Domino printer middleware."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.bootstrap import get_context
from app.version import get_version_info

api = Blueprint("api", __name__)


def _check_api_key() -> bool:
    ctx = get_context()
    expected = ctx.settings.api_key
    if not expected:
        return True
    provided = request.headers.get("X-API-Key") or request.args.get("api_key")
    return provided == expected


@api.before_request
def _auth_guard():
    if request.path in {"/health", "/version", "/"}:
        return None
    if not _check_api_key():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


@api.route("/", methods=["GET"])
def root():
    return jsonify(
        {
            "service": "domino-printer-middleware",
            "message": "Domino Ax Codenet middleware — use POST /print",
            "docs": [
                "/health",
                "/version",
                "/printers",
                "POST /test/ping",
                "POST /test/port",
                "POST /test/connection",
                "POST /print",
                "GET /job/<job_id>",
                "GET /jobs",
            ],
        }
    )


@api.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "service": "domino-printer-middleware",
            "version": get_version_info()["version"],
            "protocol": "domino_ax_codenet",
        }
    )


@api.route("/version", methods=["GET"])
def version():
    return jsonify(get_version_info())


@api.route("/printers", methods=["GET"])
def printers():
    ctx = get_context()
    return jsonify({"success": True, "printers": ctx.print_service.list_printers()})


@api.route("/test/ping", methods=["POST"])
def test_ping():
    ctx = get_context()
    result = ctx.print_service.ping_printer(request.get_json(silent=True) or {})
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@api.route("/test/port", methods=["POST"])
def test_port():
    ctx = get_context()
    result = ctx.print_service.test_port(request.get_json(silent=True) or {})
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@api.route("/test/connection", methods=["POST"])
def test_connection():
    """Ping + TCP :port + Codenet identify in one call."""
    ctx = get_context()
    result = ctx.print_service.test_connection(request.get_json(silent=True) or {})
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@api.route("/print", methods=["POST"])
def print_job():
    ctx = get_context()
    result = ctx.print_service.handle_print(request.get_json(silent=True) or {})
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@api.route("/job/<job_id>", methods=["GET"])
def get_job(job_id: str):
    ctx = get_context()
    return jsonify(ctx.print_service.get_job(job_id))


@api.route("/jobs", methods=["GET"])
def list_jobs():
    ctx = get_context()
    return jsonify(ctx.print_service.list_jobs())
