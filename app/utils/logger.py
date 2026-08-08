"""Simple rotating-friendly append logger."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock

ROOT_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

TEXT_LOG = LOG_DIR / "app.log"
JSON_LOG = LOG_DIR / "app.jsonl"
_lock = Lock()


def log(message: str, level: str = "INFO", **fields) -> None:
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] [{level}] {message}"
    if fields:
        line += " " + json.dumps(fields, ensure_ascii=False)

    with _lock:
        print(line, file=sys.stdout, flush=True)
        try:
            with TEXT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(line + os.linesep)
            payload = {"timestamp": timestamp, "level": level, "message": message, **fields}
            with JSON_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + os.linesep)
        except OSError:
            pass
