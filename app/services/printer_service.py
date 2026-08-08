"""High-level Domino print orchestration for ERP callers."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from app.core.config import PrinterConfig, Settings, load_printers_config
from app.services import codenet
from app.services.connection import DominoConnection
from app.services.connection_test import ping_host, run_connection_test, tcp_port_open
from app.utils.logger import log


class DominoPrintService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._printers: Dict[str, PrinterConfig] = {}
        self._connections: Dict[str, DominoConnection] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._jobs: Deque[Dict[str, Any]] = deque(maxlen=settings.job_history_limit)
        self._jobs_by_id: Dict[str, Dict[str, Any]] = {}
        self._registry_lock = threading.Lock()

    def load(self) -> None:
        self._printers = load_printers_config(self.settings.printers_config)
        log(f"Loaded {len(self._printers)} Domino printer(s)")

    def list_printers(self) -> Dict[str, Any]:
        return {
            pid: {
                **cfg.to_dict(),
                "connected": bool(self._connections.get(pid) and self._connections[pid].connected),
            }
            for pid, cfg in self._printers.items()
        }

    def get_job(self, job_id: str) -> Dict[str, Any]:
        job = self._jobs_by_id.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        return {"success": True, "job": job}

    def list_jobs(self, limit: int = 100) -> Dict[str, Any]:
        jobs = list(self._jobs)[-limit:]
        jobs.reverse()
        return {"success": True, "jobs": jobs}

    def test_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        printer_id = str(payload.get("printer_id") or "").strip()
        cfg = None
        if printer_id:
            cfg = self._resolve_printer(printer_id, payload.get("printer"))
        elif isinstance(payload.get("printer"), dict) or payload.get("ip"):
            cfg = None
        else:
            return {
                "success": False,
                "error": "Provide printer_id and/or ip (and optional port, default 7000)",
            }
        return run_connection_test(self.settings, payload, cfg)

    def ping_printer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        printer_id = str(payload.get("printer_id") or "").strip()
        cfg = self._printers.get(printer_id) if printer_id else None
        ip = str(
            (payload.get("printer") or {}).get("ip")
            if isinstance(payload.get("printer"), dict)
            else payload.get("ip") or (cfg.ip if cfg else "")
        ).strip()
        result = ping_host(ip)
        result["printer_id"] = printer_id or None
        return result

    def test_port(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        printer_id = str(payload.get("printer_id") or "").strip()
        cfg = self._printers.get(printer_id) if printer_id else None
        printer = payload.get("printer") if isinstance(payload.get("printer"), dict) else {}
        ip = str(printer.get("ip") or payload.get("ip") or (cfg.ip if cfg else "")).strip()
        port_raw = printer.get("port") or payload.get("port") or (cfg.port if cfg else 7000)
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = 7000
        result = tcp_port_open(ip, port, timeout_seconds=self.settings.connect_timeout)
        result["printer_id"] = printer_id or None
        return result

    def handle_print(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        printer_id = str(payload.get("printer_id") or "").strip()
        if not printer_id:
            return {"success": False, "error": "printer_id is required"}

        cfg = self._resolve_printer(printer_id, payload.get("printer"))
        if cfg is None:
            return {"success": False, "error": f"Unknown printer_id: {printer_id}"}
        if not cfg.enabled:
            return {"success": False, "error": f"Printer {printer_id} is disabled"}

        action = str(payload.get("action") or "").strip()
        if not action and isinstance(payload.get("command"), dict):
            action = str(payload["command"].get("action") or payload["command"].get("command") or "").strip()

        if not action:
            return {
                "success": False,
                "error": "action is required (e.g. print_stored_label, identify, get_status)",
            }

        job_id = str(uuid.uuid4())
        started = datetime.utcnow().isoformat() + "Z"
        try:
            result = self._run_action(cfg, action, payload)
            result.update(
                {
                    "job_id": job_id,
                    "printer_id": printer_id,
                    "protocol": "domino_ax_codenet",
                    "action": action,
                    "started_at": started,
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                }
            )
        except ValueError as exc:
            result = {
                "success": False,
                "error": str(exc),
                "job_id": job_id,
                "printer_id": printer_id,
                "protocol": "domino_ax_codenet",
                "action": action,
                "started_at": started,
                "finished_at": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as exc:  # noqa: BLE001 — surface unexpected printer/IO errors to ERP
            log(f"Domino action failed: {exc}", level="ERROR", printer_id=printer_id, action=action)
            result = {
                "success": False,
                "error": str(exc),
                "job_id": job_id,
                "printer_id": printer_id,
                "protocol": "domino_ax_codenet",
                "action": action,
                "started_at": started,
                "finished_at": datetime.utcnow().isoformat() + "Z",
            }

        self._store_job(result)
        return result

    def _resolve_printer(self, printer_id: str, printer_override: Any) -> Optional[PrinterConfig]:
        with self._registry_lock:
            cfg = self._printers.get(printer_id)
            if isinstance(printer_override, dict) and printer_override.get("ip"):
                merged = {
                    "ip": printer_override.get("ip"),
                    "port": printer_override.get("port", cfg.port if cfg else 7000),
                    "protocol": "domino_ax_codenet",
                    "default_label_slot": (cfg.default_label_slot if cfg else None),
                    "default_product_detect": (cfg.default_product_detect if cfg else "1"),
                    "enabled": True,
                    "label_map": (cfg.label_map if cfg else {}),
                }
                if cfg:
                    merged["default_label_slot"] = cfg.default_label_slot
                    merged["label_map"] = cfg.label_map
                cfg = PrinterConfig.from_dict(printer_id, merged)
                self._printers[printer_id] = cfg
            return cfg

    def _connection(self, cfg: PrinterConfig) -> DominoConnection:
        conn = self._connections.get(cfg.printer_id)
        if conn is None:
            conn = DominoConnection(cfg.printer_id, cfg.ip, cfg.port, self.settings)
            self._connections[cfg.printer_id] = conn
            self._locks[cfg.printer_id] = threading.Lock()
        else:
            conn.update_target(cfg.ip, cfg.port)
        return conn

    def _run_action(self, cfg: PrinterConfig, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(payload)
        if isinstance(payload.get("command"), dict):
            params.update(payload["command"])

        if action == "print_stored_label":
            return self._print_stored_label(cfg, params)
        if action == "print_product":
            return self._print_product(cfg, params)

        builder = codenet.COMMAND_BUILDERS.get(action)
        if not builder:
            raise ValueError(f"Unsupported action: {action}")

        command_kwargs = self._command_kwargs(action, cfg, params)
        packet = builder(**command_kwargs)
        step = self._send_step(cfg, action, packet)
        return {
            "success": step["ok"],
            "steps": [step],
            "error": None if step["ok"] else step.get("error"),
            "nak_code": step.get("nak_code"),
        }

    def _print_product(self, cfg: PrinterConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        product_code = str(params.get("product_code") or params.get("product") or "").strip()
        if not product_code:
            raise ValueError("product_code is required for print_product")
        slot = cfg.label_map.get(product_code)
        if not slot:
            raise ValueError(f"No label_slot mapped for product_code={product_code!r}")
        params = {**params, "label_slot": slot}
        return self._print_stored_label(cfg, params)

    def _print_stored_label(self, cfg: PrinterConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        label_slot = str(params.get("label_slot") or cfg.default_label_slot or "").strip()
        if not label_slot:
            raise ValueError("label_slot is required (or set default_label_slot / label_map)")
        product_detect = str(params.get("product_detect") or cfg.default_product_detect or "1")

        steps: List[Dict[str, Any]] = []
        lock = self._locks.setdefault(cfg.printer_id, threading.Lock())
        with lock:
            steps.append(self._send_step(cfg, "put_label_online", codenet.put_label_online(label_slot)))
            if not steps[-1]["ok"]:
                return {
                    "success": False,
                    "steps": steps,
                    "error": steps[-1].get("error"),
                    "nak_code": steps[-1].get("nak_code"),
                    "label_slot": label_slot,
                }
            steps.append(self._send_step(cfg, "print_go", codenet.print_go(product_detect)))

        ok = all(step["ok"] for step in steps)
        return {
            "success": ok,
            "steps": steps,
            "error": None if ok else steps[-1].get("error"),
            "nak_code": None if ok else steps[-1].get("nak_code"),
            "label_slot": label_slot,
            "product_detect": product_detect,
        }

    def _command_kwargs(self, action: str, cfg: PrinterConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "put_label_online":
            slot = params.get("label_slot") or cfg.default_label_slot
            if not slot:
                raise ValueError("label_slot is required")
            return {"label_slot": slot}
        if action == "print_go":
            return {"product_detect": params.get("product_detect") or cfg.default_product_detect}
        if action == "download_label_without_save":
            if not params.get("slot") or params.get("label_data") is None:
                raise ValueError("slot and label_data are required")
            return {"slot": params["slot"], "label_data": str(params["label_data"])}
        if action == "store_label":
            if not params.get("label_slot") or params.get("label_data") is None:
                raise ValueError("label_slot and label_data are required")
            return {"label_slot": params["label_slot"], "label_data": str(params["label_data"])}
        if action == "send_fifo_data":
            if params.get("data") is None:
                raise ValueError("data is required")
            return {"data": str(params["data"])}
        return {}

    def _send_step(self, cfg: PrinterConfig, command: str, packet: bytes) -> Dict[str, Any]:
        conn = self._connection(cfg)
        raw, transport_error = conn.send_and_receive(packet)
        if transport_error:
            return {
                "command": command,
                "hex": packet.hex().upper(),
                "ok": False,
                "error": transport_error,
                "response": "",
            }

        parsed = codenet.parse_response(raw, fixed_ack_mode=self.settings.fixed_ack_mode)
        return {
            "command": command,
            "hex": packet.hex().upper(),
            "ok": parsed.ok,
            "response": parsed.response_hex,
            "nak_code": parsed.nak_code,
            "error": parsed.error,
            "query_payload_hex": parsed.query_payload_hex,
        }

    def _store_job(self, result: Dict[str, Any]) -> None:
        self._jobs.append(result)
        self._jobs_by_id[result["job_id"]] = result
