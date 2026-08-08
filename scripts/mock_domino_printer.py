#!/usr/bin/env python3
"""Minimal Domino Codenet TCP mock for local ERP / middleware testing."""

from __future__ import annotations

import argparse
import socket
import threading

ESC, EOT, ACK, NAK = 0x1B, 0x04, 0x06, 0x15


def handle_client(conn: socket.socket, addr) -> None:
    print(f"Client connected: {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            print(f"RECV hex={data.hex().upper()}")
            if not data or data[0] != ESC or data[-1] != EOT:
                conn.sendall(bytes([NAK]) + b"002")
                continue
            body = data[1:-1]
            # Queries return a framed stub; commands return ACK.
            if body.endswith(bytes([0x3F])):
                # ESC A <type 30> EOT style stub for identify
                if body.startswith(b"A"):
                    conn.sendall(bytes([ESC]) + b"A30" + bytes([EOT]))
                else:
                    conn.sendall(bytes([ESC]) + body[:-1] + b"OK" + bytes([EOT]))
            else:
                conn.sendall(bytes([ACK]))
    finally:
        conn.close()
        print(f"Client disconnected: {addr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Domino Codenet printer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7000)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(5)
    print(f"Mock Domino listening on {args.host}:{args.port}")

    while True:
        client, addr = sock.accept()
        threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()


if __name__ == "__main__":
    main()
