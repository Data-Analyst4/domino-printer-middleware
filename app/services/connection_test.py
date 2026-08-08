"""Network and Codenet connectivity checks for Domino printers."""

from __future__ import annotations

import platform
import socket
import subprocess
import time
from typing import Any, Dict, Optional

from app.core.config import PrinterConfig, Settings
from app.services import codenet
from app.services.connection import DominoConnection


def _resolve_target(payload: Dict[str, Any], cfg: Optional[PrinterConfig]) -> Dict[str, Any]:
    printer = payload.get("printer") if isinstance(payload.get("printer"), dict) else {}
    ip = str(printer.get("ip") or payload.get("ip") or (cfg.ip if cfg else "")).strip()
    port_raw = printer.get("port") or payload.get("port") or (cfg.port if cfg else 7000)
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 7000
    return {"ip": ip, "port": port}


def ping_host(ip: str, timeout_seconds: float = 2.0) -> Dict[str, Any]:
    if not ip:
        return {"success": False, "reachable": False, "error": "ip is required"}

    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_seconds * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_seconds))), ip]

    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds + 2)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        ok = completed.returncode == 0
        return {
            "success": ok,
            "reachable": ok,
            "ip": ip,
            "elapsed_ms": elapsed_ms,
            "error": None if ok else "ping failed (host unreachable or blocked)",
            "detail": (completed.stdout or completed.stderr or "").strip()[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "reachable": False,
            "ip": ip,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc),
        }


def tcp_port_open(ip: str, port: int, timeout_seconds: float = 3.0) -> Dict[str, Any]:
    if not ip:
        return {"success": False, "open": False, "error": "ip is required"}

    started = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        sock.connect((ip, port))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "success": True,
            "open": True,
            "ip": ip,
            "port": port,
            "elapsed_ms": elapsed_ms,
            "error": None,
        }
    except OSError as exc:
        return {
            "success": False,
            "open": False,
            "ip": ip,
            "port": port,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": f"TCP connect failed: {exc}",
        }
    finally:
        try:
            sock.close()
        except OSError:
            pass


def codenet_identify(settings: Settings, ip: str, port: int, printer_id: str = "TEST") -> Dict[str, Any]:
    if not ip:
        return {"success": False, "error": "ip is required"}

    conn = DominoConnection(printer_id, ip, port, settings)
    packet = codenet.identify()
    started = time.monotonic()
    try:
        raw, transport_error = conn.send_and_receive(packet)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if transport_error:
            return {
                "success": False,
                "ip": ip,
                "port": port,
                "command_hex": packet.hex().upper(),
                "elapsed_ms": elapsed_ms,
                "error": transport_error,
            }
        parsed = codenet.parse_response(raw, fixed_ack_mode=settings.fixed_ack_mode)
        return {
            "success": parsed.ok,
            "ip": ip,
            "port": port,
            "command_hex": packet.hex().upper(),
            "response_hex": parsed.response_hex,
            "query_payload_hex": parsed.query_payload_hex,
            "elapsed_ms": elapsed_ms,
            "error": parsed.error,
            "note": "Ax-Series identity type is normally 30 in the query payload",
        }
    finally:
        conn.close()


def run_connection_test(
    settings: Settings,
    payload: Dict[str, Any],
    cfg: Optional[PrinterConfig] = None,
) -> Dict[str, Any]:
    target = _resolve_target(payload, cfg)
    ip = target["ip"]
    port = target["port"]
    if not ip:
        return {"success": False, "error": "ip is required (body.ip or printer.ip or printers.json)"}

    steps = {
        "ping": ping_host(ip),
        "tcp_port": tcp_port_open(ip, port, timeout_seconds=settings.connect_timeout),
        "codenet_identify": None,
    }

    if steps["tcp_port"]["success"]:
        steps["codenet_identify"] = codenet_identify(
            settings,
            ip,
            port,
            printer_id=str(payload.get("printer_id") or (cfg.printer_id if cfg else "TEST")),
        )
    else:
        steps["codenet_identify"] = {
            "success": False,
            "skipped": True,
            "error": "skipped because TCP port is closed",
            "ip": ip,
            "port": port,
        }

    overall = bool(
        steps["ping"]["success"]
        and steps["tcp_port"]["success"]
        and steps["codenet_identify"].get("success")
    )
    return {
        "success": overall,
        "printer_id": payload.get("printer_id") or (cfg.printer_id if cfg else None),
        "ip": ip,
        "port": port,
        "protocol": "domino_ax_codenet",
        "steps": steps,
        "ready_for_print": bool(steps["tcp_port"]["success"] and steps["codenet_identify"].get("success")),
        "hint": (
            "Printer is reachable over Codenet. Next: POST /print with action identify/get_status "
            "or print_stored_label."
            if overall
            else "Fix network/Codenet settings on Domino (protocol=Codenet, TCP, port 7000, enabled)."
        ),
    }
