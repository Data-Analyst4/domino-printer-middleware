"""High-level Domino print orchestration for ERP callers."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from app.core.config import PrinterConfig, Settings, load_printers_config
from app.services import codenet
from app.services.camera_import_forwarder import (
    CAMERA_FIFO_ACTIONS,
    forward_camera_import_immediate,
    resolve_camera_target,
)
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

        # Optional camera: only for FIFO OE actions, before Domino send (Rynan-compatible).
        camera_import_meta = None
        if action in CAMERA_FIFO_ACTIONS:
            cam_url, _cam_barcode = resolve_camera_target(payload)
            if cam_url is not None:
                params = dict(payload)
                if isinstance(payload.get("command"), dict):
                    params.update(payload["command"])
                try:
                    fifo_text = self._fifo_csv(params)
                except ValueError:
                    fifo_text = ""
                camera_import_meta = forward_camera_import_immediate(
                    job_id,
                    payload,
                    fifo_text,
                    printer_id=printer_id,
                )

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

        if camera_import_meta is not None:
            result["camera_import"] = camera_import_meta

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
        if action == "get_print_count":
            return self._get_print_count(cfg, params)

        builder = codenet.COMMAND_BUILDERS.get(action)
        if not builder:
            raise ValueError(f"Unsupported action: {action}")

        command_kwargs = self._command_kwargs(action, cfg, params)
        packet = builder(**command_kwargs)
        if action != "print_go" and action not in {"print_stored_label", "print_product"}:
            if codenet.is_print_go_packet(packet):
                raise RuntimeError(f"Refusing to send Print Go (N) for action={action}")
        step = self._send_step(cfg, action, packet)
        result: Dict[str, Any] = {
            "success": step["ok"],
            "steps": [step],
            "error": None if step["ok"] else step.get("error"),
            "nak_code": step.get("nak_code"),
        }
        result.update(self._action_extras(action, command_kwargs, step))
        return result

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
        if action == "put_named_label_online":
            name = params.get("label_name") or params.get("label") or params.get("template")
            if not str(name or "").strip():
                raise ValueError("label_name is required")
            return {"label_name": str(name).strip()}
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
        if action in {"send_fifo_data", "push_fifo_fields"}:
            return {"data": self._fifo_csv(params)}
        if action == "query_product_count":
            raw = params.get("counter_id", params.get("counter", 2))
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                cid = 2
            if cid not in (1, 2):
                raise ValueError("counter_id must be 1 or 2")
            return {"counter_id": cid}
        return {}

    def _get_print_count(self, cfg: PrinterConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read T1 (photocell) and T2 (prints since power-on) for ERP printed = T2_after − T2_before."""
        steps: List[Dict[str, Any]] = []
        lock = self._locks.setdefault(cfg.printer_id, threading.Lock())
        with lock:
            for cid, name in ((1, "t1_photocell"), (2, "t2_prints")):
                packet = codenet.query_product_count(cid)
                step = self._send_step(cfg, f"query_product_count_{cid}", packet)
                count = None
                if step.get("ok"):
                    count = codenet.parse_product_count(step.get("query_payload_hex"), counter_id=cid)
                step["counter_id"] = cid
                step["counter_name"] = name
                step["count"] = count
                steps.append(step)

        t1 = steps[0].get("count") if len(steps) > 0 else None
        t2 = steps[1].get("count") if len(steps) > 1 else None
        ok = all(s.get("ok") for s in steps) and t2 is not None
        return {
            "success": ok,
            "steps": steps,
            "t1": t1,
            "t2": t2,
            "t1_photocell": t1,
            "t2_prints": t2,
            "error": None if ok else (steps[-1].get("error") if steps else "Failed to read print counters"),
            "nak_code": None if ok else (steps[-1].get("nak_code") if steps else None),
        }

    @staticmethod
    def _fifo_csv(params: Dict[str, Any]) -> str:
        """Build OE ASCII payload. Prefer fields[] (POD order), then csv, then data."""
        if params.get("fields") is not None:
            fields = params["fields"]
            if not isinstance(fields, (list, tuple)):
                raise ValueError("fields must be an array")
            return ",".join("" if item is None else str(item) for item in fields)
        if params.get("csv") is not None:
            return str(params["csv"])
        if params.get("data") is not None:
            return str(params["data"])
        raise ValueError("fields[], csv, or data is required")

    @staticmethod
    def _action_extras(action: str, kwargs: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
        extras: Dict[str, Any] = {}
        if action == "put_named_label_online":
            extras["label_name"] = kwargs.get("label_name")
        if action in {"push_fifo_fields", "send_fifo_data"}:
            extras["csv"] = kwargs.get("data")
        if action == "query_online_label":
            ascii_payload = codenet.query_payload_ascii(step.get("query_payload_hex"))
            extras["query_payload_ascii"] = ascii_payload
            extras["online_label"] = codenet.online_label_from_query_ascii(ascii_payload)
        if action == "query_product_count":
            ascii_payload = codenet.query_payload_ascii(step.get("query_payload_hex"))
            extras["query_payload_ascii"] = ascii_payload
            extras["counter_id"] = kwargs.get("counter_id", 2)
            extras["count"] = codenet.parse_product_count(
                step.get("query_payload_hex"),
                counter_id=kwargs.get("counter_id"),
            )
        return extras

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
