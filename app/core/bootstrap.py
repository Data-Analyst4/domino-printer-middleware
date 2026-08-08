"""Application bootstrap for Domino middleware."""

from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from app.core.config import Settings
from app.services.printer_service import DominoPrintService
from app.utils.logger import log


@dataclass
class AppContext:
    settings: Settings
    print_service: DominoPrintService


_context: Optional[AppContext] = None
_lock = threading.Lock()


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("Application not initialized")
    return _context


def init_app(env_file: Optional[str] = None) -> AppContext:
    global _context
    with _lock:
        if _context is not None:
            return _context

        load_dotenv(env_file)
        settings = Settings.from_env()
        print_service = DominoPrintService(settings)
        print_service.load()

        _context = AppContext(settings=settings, print_service=print_service)
        atexit.register(shutdown_app)
        log("Domino printer middleware initialized", port=settings.port)
        return _context


def shutdown_app() -> None:
    global _context
    with _lock:
        if _context is None:
            return
        _context = None
        log("Domino printer middleware shut down")
