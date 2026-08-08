"""Configuration for Domino printer middleware."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 5003
    cors_origins: str = "*"
    printers_config: str = str(ROOT_DIR / "config" / "printers.json")
    api_key: Optional[str] = None
    connect_timeout: float = 5.0
    read_timeout: float = 5.0
    send_retries: int = 3
    fixed_ack_mode: bool = False
    job_history_limit: int = 1000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=_env_int("PORT", 5003),
            cors_origins=os.getenv("CORS_ORIGINS", "*"),
            printers_config=os.getenv("PRINTERS_CONFIG", str(ROOT_DIR / "config" / "printers.json")),
            api_key=os.getenv("API_KEY") or None,
            connect_timeout=_env_float("PRINTER_CONNECT_TIMEOUT", 5.0),
            read_timeout=_env_float("PRINTER_READ_TIMEOUT", 5.0),
            send_retries=max(1, _env_int("PRINTER_SEND_RETRIES", 3)),
            fixed_ack_mode=_env_bool("DOMINO_FIXED_ACK_MODE", False),
            job_history_limit=_env_int("JOB_HISTORY_LIMIT", 1000),
        )


@dataclass
class PrinterConfig:
    printer_id: str
    ip: str
    port: int = 7000
    protocol: str = "domino_ax_codenet"
    default_label_slot: Optional[str] = None
    default_product_detect: str = "1"
    enabled: bool = True
    label_map: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, printer_id: str, data: Dict[str, Any]) -> "PrinterConfig":
        label_map = data.get("label_map") or {}
        if not isinstance(label_map, dict):
            label_map = {}
        return cls(
            printer_id=printer_id,
            ip=str(data["ip"]),
            port=int(data.get("port", 7000)),
            protocol=str(data.get("protocol", "domino_ax_codenet")),
            default_label_slot=data.get("default_label_slot"),
            default_product_detect=str(data.get("default_product_detect", "1")),
            enabled=bool(data.get("enabled", True)),
            label_map={str(k): str(v) for k, v in label_map.items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "port": self.port,
            "protocol": self.protocol,
            "default_label_slot": self.default_label_slot,
            "default_product_detect": self.default_product_detect,
            "enabled": self.enabled,
            "label_map": self.label_map,
        }


def load_printers_config(path: str) -> Dict[str, PrinterConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return {}

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    printers: Dict[str, PrinterConfig] = {}
    for printer_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            printers[printer_id] = PrinterConfig.from_dict(printer_id, entry)
        except (KeyError, TypeError, ValueError):
            continue
    return printers
