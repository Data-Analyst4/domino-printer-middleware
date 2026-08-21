"""Tests for demo Domino mock response mapping (no TCP)."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from mock_domino_printer import (  # noqa: E402
    DemoPrinterState,
    build_response,
)


class DemoPrinterResponseTests(unittest.TestCase):
    def setUp(self):
        self.state = DemoPrinterState()

    def test_identify_success(self):
        resp, summary = build_response(b"A?", self.state, False)
        self.assertEqual(resp.hex().upper(), "1B41333004")
        self.assertIn("identify", summary)

    def test_codenet_version_success(self):
        resp, _ = build_response(b"}D?", self.state, False)
        self.assertTrue(resp.startswith(bytes([0x1B, 0x7D, 0x44])))
        self.assertTrue(resp.endswith(bytes([0x04])))

    def test_status_queries_success(self):
        basic, _ = build_response(b"1C?", self.state, False)
        ext, _ = build_response(b"O1?", self.state, False)
        self.assertEqual(basic[0], 0x1B)
        self.assertEqual(ext[0], 0x1B)
        self.assertTrue(basic.endswith(bytes([0x04])))
        self.assertTrue(ext.endswith(bytes([0x04])))

    def test_put_label_and_print_ack(self):
        put, _ = build_response(b"P001", self.state, False)
        go, _ = build_response(b"N1", self.state, False)
        self.assertEqual(put, bytes([0x06]))
        self.assertEqual(go, bytes([0x06]))
        self.assertEqual(self.state.print_count, 1)

    def test_fixed_ack_mode(self):
        put, _ = build_response(b"P001", self.state, True)
        self.assertEqual(put.hex().upper(), "06303030")

    def test_missing_label_nak(self):
        resp, summary = build_response(b"P999", self.state, False)
        self.assertEqual(resp[0], 0x15)
        self.assertIn("016", summary)

    def test_store_label_then_online(self):
        store, _ = build_response(b"S003HELLO", self.state, False)
        self.assertEqual(store, bytes([0x06]))
        put, _ = build_response(b"P003", self.state, False)
        self.assertEqual(put, bytes([0x06]))
        self.assertEqual(self.state.online_slot, "003")

    def test_fifo_success(self):
        # OE + 0004 + ABCD
        resp, summary = build_response(b"OE0004ABCD", self.state, False)
        self.assertEqual(resp, bytes([0x06]))
        self.assertIn("fifo", summary)

    def test_named_label_online_and_truncated_query(self):
        put, _ = build_response(b"ON114NOICE KM 200ML", self.state, False)
        self.assertEqual(put, bytes([0x06]))
        self.assertEqual(self.state.online_name, "NOICE KM 200ML")
        query, _ = build_response(b"P1?", self.state, False)
        self.assertEqual(query, bytes.fromhex("1B50314E4F4904"))  # P1NOI

    def test_soft_stop_and_resume(self):
        stop, _ = build_response(b"Q1N", self.state, False)
        self.assertEqual(stop, bytes([0x06]))
        self.assertFalse(self.state.head_enabled)
        resume, _ = build_response(b"Q1Y", self.state, False)
        self.assertEqual(resume, bytes([0x06]))
        self.assertTrue(self.state.head_enabled)


if __name__ == "__main__":
    unittest.main()
