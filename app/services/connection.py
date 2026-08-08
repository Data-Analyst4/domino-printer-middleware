"""Binary TCP transport for Domino Codenet."""

from __future__ import annotations

import socket
import threading
from typing import Optional, Tuple

from app.core.config import Settings
from app.utils.logger import log


class DominoConnection:
    def __init__(self, printer_id: str, host: str, port: int, settings: Settings):
        self.printer_id = printer_id
        self.host = host
        self.port = port
        self.settings = settings
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def update_target(self, host: str, port: int) -> None:
        with self._lock:
            if self.host != host or self.port != port:
                self._close_unlocked()
                log(f"Printer {self.printer_id} target updated: {self.host}:{self.port} -> {host}:{port}")
            self.host = host
            self.port = port

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _connect_unlocked(self) -> socket.socket:
        if self._sock is not None:
            return self._sock

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.settings.connect_timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as exc:
            raise ConnectionError(f"TCP connect failed for {self.host}:{self.port}: {exc}") from exc

        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        log(f"TCP connected {self.printer_id} -> {self.host}:{self.port}")
        return sock

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def send_and_receive(self, payload: bytes) -> Tuple[bytes, Optional[str]]:
        with self._lock:
            last_error: Optional[str] = None
            for attempt in range(1, self.settings.send_retries + 1):
                try:
                    sock = self._connect_unlocked()
                    sock.sendall(payload)
                    sock.settimeout(self.settings.read_timeout)
                    data = sock.recv(4096)
                    if not data:
                        self._close_unlocked()
                        last_error = "empty_response"
                        continue
                    return data, None
                except socket.timeout:
                    self._close_unlocked()
                    last_error = "read_timeout"
                except ConnectionError:
                    self._close_unlocked()
                    last_error = "connect_error"
                except OSError:
                    self._close_unlocked()
                    last_error = "connect_error"
                log(
                    f"Domino send attempt {attempt}/{self.settings.send_retries} failed",
                    level="WARNING",
                    printer_id=self.printer_id,
                    error=last_error,
                )
            return b"", last_error
