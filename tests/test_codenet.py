"""Unit tests for Domino Codenet framing (no printer required)."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services import codenet


class CodenetTests(unittest.TestCase):
    def test_identify(self):
        self.assertEqual(codenet.identify().hex().upper(), "1B413F04")

    def test_put_label_and_print(self):
        self.assertEqual(codenet.put_label_online("9").hex().upper(), "1B5030303904")
        self.assertEqual(codenet.print_go("1").hex().upper(), "1B4E3104")

    def test_parse_ack_nak(self):
        ack = codenet.parse_response(bytes([0x06]))
        self.assertTrue(ack.ok)
        nak = codenet.parse_response(bytes([0x15]) + b"007")
        self.assertFalse(nak.ok)
        self.assertEqual(nak.nak_code, "007")


if __name__ == "__main__":
    unittest.main()
