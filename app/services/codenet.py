"""Domino Ax-Series Codenet 2 command builder and response parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ESC = 0x1B
EOT = 0x04
ACK = 0x06
NAK = 0x15
QUERY = ord("?")

NAK_MESSAGES = {
    "001": "Invalid command length",
    "002": "Invalid command header, ESC expected",
    "003": "Unrecognised command code following ESC",
    "004": "Unexpected characters before EOT",
    "005": "Invalid head selector",
    "007": "Command parameter out of permitted range",
    "008": "Print label number out of range",
    "009": "Syntax error",
    "010": "Print label too long for label store",
    "011": "Print label too long for print buffer",
    "012": "Invalid embedded format command",
    "013": "Invalid character in print label",
    "016": "Cannot load label",
    "017": "Specified print label number is invalid",
    "020": "Command not implemented",
    "024": "Checksum error",
    "027": "Command rejected, printing disabled",
    "050": "Printer busy with auto repeat de-assert photocell",
    "051": "Internal printer error",
    "052": "Requested file could not be found",
}


@dataclass
class CodenetResult:
    ok: bool
    response_hex: str
    ack: bool = False
    nak_code: Optional[str] = None
    error: Optional[str] = None
    query_payload_hex: Optional[str] = None
    raw: bytes = b""


def _frame(*parts: bytes) -> bytes:
    return bytes([ESC]) + b"".join(parts) + bytes([EOT])


def _slot3(slot: str) -> bytes:
    text = str(slot).strip()
    if not text.isdigit():
        raise ValueError(f"label_slot must be numeric, got {slot!r}")
    return f"{int(text):03d}".encode("ascii")


def identify() -> bytes:
    return _frame(b"A", bytes([QUERY]))


def get_codenet_version() -> bytes:
    return _frame(b"}D", bytes([QUERY]))


def get_basic_status() -> bytes:
    return _frame(b"1C", bytes([QUERY]))


def get_extended_status() -> bytes:
    return _frame(b"O1", bytes([QUERY]))


def put_label_online(label_slot: str) -> bytes:
    return _frame(b"P", _slot3(label_slot))


def print_go(product_detect: str = "1") -> bytes:
    detect = str(product_detect).strip() or "1"
    if len(detect) != 1 or not detect.isdigit():
        raise ValueError(f"product_detect must be a single digit, got {product_detect!r}")
    return _frame(b"N", detect.encode("ascii"))


def download_label_without_save(slot: str, label_data: str) -> bytes:
    data = label_data.encode("ascii", errors="strict")
    return _frame(b"OQ", _slot3(slot), data)


def send_fifo_data(data: str) -> bytes:
    payload = data.encode("ascii", errors="strict")
    length = f"{len(payload):04d}".encode("ascii")
    return _frame(b"OE", length, payload)


def store_label(label_slot: str, label_data: str) -> bytes:
    data = label_data.encode("ascii", errors="strict")
    return _frame(b"S", _slot3(label_slot), data)


def parse_response(raw: bytes, *, fixed_ack_mode: bool = False) -> CodenetResult:
    response_hex = raw.hex().upper() if raw else ""
    if not raw:
        return CodenetResult(ok=False, response_hex=response_hex, error="Empty response from printer", raw=raw)

    if raw[0] == ACK:
        return CodenetResult(ok=True, response_hex=response_hex, ack=True, raw=raw)

    if raw[0] == NAK:
        code = None
        if len(raw) >= 4:
            try:
                code = raw[1:4].decode("ascii")
            except UnicodeDecodeError:
                code = None
        message = NAK_MESSAGES.get(code or "", "Printer rejected command")
        if code:
            message = f"{message} (NAK {code})"
        return CodenetResult(
            ok=False,
            response_hex=response_hex,
            nak_code=code,
            error=message,
            raw=raw,
        )

    if raw[0] == ESC and raw[-1] == EOT:
        inner = raw[1:-1]
        return CodenetResult(
            ok=True,
            response_hex=response_hex,
            query_payload_hex=inner.hex().upper(),
            raw=raw,
        )

    if fixed_ack_mode and response_hex.startswith("06303030"):
        return CodenetResult(ok=True, response_hex=response_hex, ack=True, raw=raw)

    return CodenetResult(
        ok=False,
        response_hex=response_hex,
        error=f"Unrecognized printer response: {response_hex}",
        raw=raw,
    )


COMMAND_BUILDERS = {
    "identify": lambda **_: identify(),
    "get_codenet_version": lambda **_: get_codenet_version(),
    "get_status": lambda **_: get_extended_status(),
    "get_basic_status": lambda **_: get_basic_status(),
    "get_extended_status": lambda **_: get_extended_status(),
    "put_label_online": lambda **kw: put_label_online(kw["label_slot"]),
    "print_go": lambda **kw: print_go(kw.get("product_detect", "1")),
    "download_label_without_save": lambda **kw: download_label_without_save(kw["slot"], kw["label_data"]),
    "send_fifo_data": lambda **kw: send_fifo_data(kw["data"]),
    "store_label": lambda **kw: store_label(kw["label_slot"], kw["label_data"]),
}
