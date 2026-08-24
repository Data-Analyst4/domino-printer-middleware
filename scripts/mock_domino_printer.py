#!/usr/bin/env python3
"""
Demo Domino Ax-Series Codenet TCP printer.

Mimics a successful printer on port 7000 so middleware / ERP can be tested
without hardware. Speaks the same framing the real middleware expects:

  request:  ESC <command...> EOT   (1B ... 04)
  success:  ACK (06)  or  ESC <payload> EOT for queries
  failure:  NAK (15) + 3-digit code

Pre-seeded label slots: 001, 002 (matching printers.json.example label_map).

Usage:
  python scripts/mock_domino_printer.py
  python scripts/mock_domino_printer.py --host 0.0.0.0 --port 7000
  python scripts/mock_domino_printer.py --fixed-ack   # ACK as 06 30 30 30
"""

from __future__ import annotations

import argparse
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

ESC, EOT, ACK, NAK, QUERY = 0x1B, 0x04, 0x06, 0x15, ord("?")

# Realistic Ax-Series identity / status stubs (ASCII inside ESC…EOT frame).
AX_PRINTER_TYPE = b"30"  # Ax-Series type code from Domino manual
CODENET_VERSION = b"2.0"
# Extended status: ready + green LED style stub
BASIC_STATUS = b"000110000"  # 3-digit code + ink-jet id + change time stub
EXTENDED_STATUS = b"0001"  # ready / cabinet LED stub


@dataclass
class DemoPrinterState:
    """In-memory label store + counters, shared across client threads."""

    labels: Dict[str, str] = field(
        default_factory=lambda: {
            "001": "DEMO_LABEL_001",
            "002": "DEMO_LABEL_002",
        }
    )
    named_labels: Dict[str, str] = field(
        default_factory=lambda: {
            "NOICE KM 200ML": "DEMO_NAMED_NOICE",
        }
    )
    online_slot: Optional[str] = "001"
    online_name: Optional[str] = None
    head_enabled: bool = True
    print_count: int = 0
    command_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


def _frame(payload: bytes) -> bytes:
    return bytes([ESC]) + payload + bytes([EOT])


def _ack(fixed_ack: bool) -> bytes:
    if fixed_ack:
        return bytes([ACK]) + b"000"
    return bytes([ACK])


def _nak(code: str) -> bytes:
    return bytes([NAK]) + code.encode("ascii")


def _slot3(raw: bytes) -> Optional[str]:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not text.isdigit() or len(text) < 3:
        return None
    return f"{int(text[:3]):03d}"


def build_response(
    body: bytes,
    state: DemoPrinterState,
    fixed_ack: bool,
    *,
    fail_unknown: bool = False,
) -> Tuple[bytes, str]:
    """
    Map one Codenet command body (bytes between ESC and EOT) to a reply.
    Returns (response_bytes, human_summary).
    """
    if not body:
        return _nak("001"), "empty body -> NAK 001"

    # --- Queries (end with ?) ---
    if body[-1] == QUERY:
        cmd = body[:-1]

        # A? — printer identity (Ax type 30)
        if cmd == b"A":
            return _frame(b"A" + AX_PRINTER_TYPE), "identify -> Ax type 30"

        # }D? — Codenet version
        if cmd == b"}D":
            return _frame(b"}D" + CODENET_VERSION), "codenet version -> 2.0"

        # 1C? — basic / current status
        if cmd == b"1C":
            return _frame(b"1C" + BASIC_STATUS), "basic status -> ready"

        # O1? — extended status
        if cmd == b"O1":
            return _frame(b"O1" + EXTENDED_STATUS), "extended status -> ready"

        # P1? — currently online label (named labels echo a truncated name, as on the Ax)
        if cmd == b"P1":
            with state.lock:
                source = state.online_name or state.online_slot or ""
            echo = source[:3].encode("ascii", errors="replace")
            return _frame(b"P1" + echo), f"query_online_label -> P1{source[:3]!r}"

        # Q1? — head enable (Y) / soft-stopped (N)
        if cmd == b"Q1":
            flag = b"Y" if state.head_enabled else b"N"
            return _frame(b"Q1" + flag), f"head query -> Q1{flag.decode()}"

        # T1? / T2? — product / print counters (T2 = prints since power-on)
        if cmd in {b"T1", b"T2"}:
            cid = 1 if cmd == b"T1" else 2
            value = 304641327 if cid == 1 else 138
            payload = f"T{cid}{value:010d}".encode("ascii")
            return _frame(payload), f"query_product_count T{cid} -> {value}"

        # Generic query echo (success-shaped)
        return _frame(cmd + b"OK"), f"query {cmd!r} -> OK stub"

    # --- Commands (ACK on success) ---

    # P + 3-digit slot — put stored label online
    if body.startswith(b"P"):
        slot = _slot3(body[1:4]) if len(body) >= 4 else None
        if slot is None:
            return _nak("007"), "put_label_online -> NAK 007 (bad slot)"
        with state.lock:
            if slot not in state.labels:
                return _nak("016"), f"put_label_online {slot} -> NAK 016 (not found)"
            state.online_slot = slot
        return _ack(fixed_ack), f"put_label_online {slot} -> ACK"

    # N + product detect digit — print go
    if body.startswith(b"N"):
        if len(body) != 2 or not body[1:2].isdigit():
            return _nak("007"), "print_go -> NAK 007 (bad product_detect)"
        with state.lock:
            if not state.online_slot:
                return _nak("027"), "print_go -> NAK 027 (no label online)"
            state.print_count += 1
            count = state.print_count
            slot = state.online_slot
        return _ack(fixed_ack), f"print_go slot={slot} #{count} -> ACK"

    # S + slot + data — store label
    if body.startswith(b"S"):
        if len(body) < 4:
            return _nak("001"), "store_label -> NAK 001"
        slot = _slot3(body[1:4])
        if slot is None:
            return _nak("017"), "store_label -> NAK 017"
        try:
            data = body[4:].decode("ascii")
        except UnicodeDecodeError:
            return _nak("013"), "store_label -> NAK 013"
        with state.lock:
            state.labels[slot] = data
        return _ack(fixed_ack), f"store_label {slot} ({len(data)} bytes) -> ACK"

    # OQ + slot + data — download label without save (still ACK success for demo)
    if body.startswith(b"OQ"):
        if len(body) < 5:
            return _nak("001"), "download_label -> NAK 001"
        slot = _slot3(body[2:5])
        if slot is None:
            return _nak("007"), "download_label -> NAK 007"
        return _ack(fixed_ack), f"download_label_without_save {slot} -> ACK"

    # OE + 4-digit length + data — FIFO external data
    if body.startswith(b"OE"):
        if len(body) < 6:
            return _nak("001"), "fifo -> NAK 001"
        length_text = body[2:6]
        if not length_text.isdigit():
            return _nak("007"), "fifo -> NAK 007"
        expected = int(length_text)
        payload = body[6:]
        if len(payload) != expected:
            return _nak("001"), f"fifo -> NAK 001 (len {len(payload)} != {expected})"
        return _ack(fixed_ack), f"send_fifo_data {expected} bytes -> ACK"

    # ON + head + 2-digit length + name — named label online (no Print Go)
    if body.startswith(b"ON"):
        if len(body) < 5:
            return _nak("001"), "put_named_label_online -> NAK 001"
        if body[2:3] != b"1":
            return _nak("005"), "put_named_label_online -> NAK 005 (head)"
        length_text = body[3:5]
        if not length_text.isdigit():
            return _nak("007"), "put_named_label_online -> NAK 007"
        expected = int(length_text)
        name_bytes = body[5:]
        if len(name_bytes) != expected:
            return _nak("001"), "put_named_label_online -> NAK 001 (length)"
        try:
            name = name_bytes.decode("ascii")
        except UnicodeDecodeError:
            return _nak("013"), "put_named_label_online -> NAK 013"
        with state.lock:
            if state.named_labels and name not in state.named_labels:
                return _nak("016"), f"put_named_label_online {name!r} -> NAK 016"
            state.online_name = name
        return _ack(fixed_ack), f"put_named_label_online {name!r} -> ACK"

    # Q1N / Q1Y — soft stop / resume (no Print Go, jet stays up)
    if body in {b"Q1N", b"Q1Y"}:
        with state.lock:
            state.head_enabled = body.endswith(b"Y")
        return _ack(fixed_ack), f"head {'enable' if body.endswith(b'Y') else 'disable'} -> ACK"

    # OS 0 / OS 1 / OS ? — jet sequence off / on / query (UI Start / Sequence off)
    if body in {b"OS0", b"OS1"}:
        return _ack(fixed_ack), f"sequence {'on' if body.endswith(b'1') else 'off'} -> ACK"
    if body == b"OS?":
        # Minimal query echo: OS + state digit 1 (Ready)
        return bytes([ESC]) + b"OS1" + bytes([EOT]), "query_sequence -> OS1"

    # Unknown command — ACK by default so exploratory demos stay green
    if fail_unknown:
        return _nak("003"), f"unknown command {body[:8]!r}… -> NAK 003"
    return _ack(fixed_ack), f"unknown command {body[:8]!r}… -> ACK (demo)"


def handle_client(
    conn: socket.socket,
    addr,
    state: DemoPrinterState,
    fixed_ack: bool,
    fail_unknown: bool = False,
) -> None:
    peer = f"{addr[0]}:{addr[1]}"
    print(f"[{_ts()}] CONNECT  {peer}")
    try:
        while True:
            data = conn.recv(8192)
            if not data:
                break

            with state.lock:
                state.command_count += 1
                n = state.command_count

            hex_in = data.hex().upper()
            print(f"[{_ts()}] RECV#{n}  {peer}  hex={hex_in}")

            if data[0] != ESC:
                resp = _nak("002")
                summary = "NAK 002 (ESC expected)"
            elif data[-1] != EOT:
                resp = _nak("004")
                summary = "NAK 004 (EOT expected)"
            else:
                resp, summary = build_response(
                    data[1:-1], state, fixed_ack, fail_unknown=fail_unknown
                )

            conn.sendall(resp)
            print(f"[{_ts()}] SEND#{n}  {peer}  hex={resp.hex().upper()}  ({summary})")
    except OSError as exc:
        print(f"[{_ts()}] ERROR   {peer}  {exc}")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        print(f"[{_ts()}] CLOSE   {peer}")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo Domino Ax Codenet printer (successful responses)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7000, help="Codenet TCP port (default 7000)")
    parser.add_argument(
        "--fixed-ack",
        action="store_true",
        help="Reply ACK as 06303030 (fixed-length ACK mode)",
    )
    parser.add_argument(
        "--fail-unknown",
        action="store_true",
        help="NAK unknown commands instead of ACK (stricter demo)",
    )
    args = parser.parse_args()

    state = DemoPrinterState()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(8)

    print("=" * 60)
    print("  Demo Domino Ax-Series printer (Codenet TCP)")
    print("=" * 60)
    print(f"  Listening:   {args.host}:{args.port}")
    print(f"  Identity:    Ax type {AX_PRINTER_TYPE.decode()} (success)")
    print(f"  ACK mode:    {'fixed 06303030' if args.fixed_ack else 'single-byte 06'}")
    print(f"  Labels:      {', '.join(sorted(state.labels))} (pre-seeded)")
    print()
    print("  Point middleware config/printers.json at this host:")
    print('    "ip": "127.0.0.1", "port": 7000')
    print()
    print("  Then:")
    print("    curl http://127.0.0.1:5003/health")
    print('    curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" \\')
    print('      -d "{\\"ip\\":\\"127.0.0.1\\",\\"port\\":7000}"')
    print("  Ctrl+C to stop.")
    print("=" * 60)

    try:
        while True:
            client, addr = sock.accept()
            threading.Thread(
                target=handle_client,
                args=(client, addr, state, args.fixed_ack, args.fail_unknown),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] Shutting down demo printer "
              f"(commands={state.command_count}, prints={state.print_count})")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
