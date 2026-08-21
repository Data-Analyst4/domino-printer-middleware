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
        self.assertTrue(codenet.is_print_go_packet(codenet.print_go("1")))

    def test_named_label_online_matches_live_probe(self):
        packet = codenet.put_named_label_online("NOICE KM 200ML")
        self.assertEqual(
            packet.hex().upper(),
            "1B4F4E3131344E4F494345204B4D203230304D4C04",
        )
        self.assertFalse(codenet.is_print_go_packet(packet))

    def test_query_online_label_matches_live_probe(self):
        packet = codenet.query_online_label()
        self.assertEqual(packet.hex().upper(), "1B50313F04")
        self.assertFalse(codenet.is_print_go_packet(packet))
        self.assertEqual(codenet.online_label_from_query_ascii("P1NOI"), "NOI")

    def test_soft_stop_resume_match_live_probe(self):
        self.assertEqual(codenet.soft_stop().hex().upper(), "1B51314E04")
        self.assertEqual(codenet.soft_resume().hex().upper(), "1B51315904")
        self.assertFalse(codenet.is_print_go_packet(codenet.soft_stop()))
        self.assertFalse(codenet.is_print_go_packet(codenet.soft_resume()))

    def test_fifo_oe_no_print_go(self):
        packet = codenet.send_fifo_data("95.00,KFBNIKHIL7,11/08/2026,10/05/2027")
        self.assertTrue(packet.hex().upper().startswith("1B4F45"))
        self.assertFalse(codenet.is_print_go_packet(packet))

    def test_parse_ack_nak(self):
        ack = codenet.parse_response(bytes([0x06]))
        self.assertTrue(ack.ok)
        nak = codenet.parse_response(bytes([0x15]) + b"007")
        self.assertFalse(nak.ok)
        self.assertEqual(nak.nak_code, "007")


if __name__ == "__main__":
    unittest.main()
