"""ERP photocell job path — HTTP + Codenet builders, no live Ax."""

from __future__ import annotations

import os
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
for path in (ROOT, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.core.config import PrinterConfig, Settings  # noqa: E402
from app.services import codenet  # noqa: E402
from app.services.printer_service import DominoPrintService  # noqa: E402
from mock_domino_printer import DemoPrinterState, build_response  # noqa: E402

ERP_PRINTER_ID = "DOMINO_AX_1"
LABEL_NAME = "NOICE KM 200ML"
BOTTLE_FIELDS = ["95.00", "KFBNIKHIL7", "11/08/2026", "10/05/2027"]
BOTTLE_CSV = "95.00,KFBNIKHIL7,11/08/2026,10/05/2027"


class FakeDominoConnection:
    """In-process Codenet replies. Never opens a TCP socket."""

    connected = True

    def __init__(self) -> None:
        self.state = DemoPrinterState()
        self.sent = []

    def update_target(self, host: str, port: int) -> None:
        return None

    def send_and_receive(self, payload: bytes):
        self.sent.append(payload)
        if not payload or payload[0] != 0x1B or payload[-1] != 0x04:
            return bytes([0x15]) + b"002", None
        resp, _ = build_response(payload[1:-1], self.state, False)
        return resp, None


def _service_with_fake():
    settings = Settings()
    svc = DominoPrintService(settings)
    cfg = PrinterConfig(printer_id=ERP_PRINTER_ID, ip="127.0.0.1", port=9)
    svc._printers = {ERP_PRINTER_ID: cfg}
    fake = FakeDominoConnection()
    svc._connections[ERP_PRINTER_ID] = fake
    svc._locks[ERP_PRINTER_ID] = threading.Lock()
    return svc, fake


class FifoCsvTests(unittest.TestCase):
    def test_fields_preferred_over_csv(self):
        csv = DominoPrintService._fifo_csv(
            {"fields": BOTTLE_FIELDS, "csv": "ignored"}
        )
        self.assertEqual(csv, BOTTLE_CSV)

    def test_csv_then_data_aliases(self):
        self.assertEqual(DominoPrintService._fifo_csv({"csv": BOTTLE_CSV}), BOTTLE_CSV)
        self.assertEqual(DominoPrintService._fifo_csv({"data": "BATCH123"}), "BATCH123")

    def test_missing_payload_raises(self):
        with self.assertRaises(ValueError):
            DominoPrintService._fifo_csv({})


class ErpJobPathServiceTests(unittest.TestCase):
    def setUp(self):
        self.svc, self.fake = _service_with_fake()

    def _print(self, payload):
        return self.svc.handle_print({"printer_id": ERP_PRINTER_ID, **payload})

    def test_put_named_label_online(self):
        result = self._print({"action": "put_named_label_online", "label_name": LABEL_NAME})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["action"], "put_named_label_online")
        self.assertEqual(result["label_name"], LABEL_NAME)
        self.assertEqual(
            result["steps"][0]["hex"],
            "1B4F4E3131344E4F494345204B4D203230304D4C04",
        )
        self.assertEqual(result["steps"][0]["response"], "06")

    def test_query_online_label_truncated_echo(self):
        self._print({"action": "put_named_label_online", "label_name": LABEL_NAME})
        result = self._print({"action": "query_online_label"})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["query_payload_ascii"], "P1NOI")
        self.assertEqual(result["online_label"], "NOI")
        self.assertEqual(result["steps"][0]["hex"], "1B50313F04")

    def test_push_fifo_fields_and_send_fifo_data_alias(self):
        from_fields = self._print({"action": "push_fifo_fields", "fields": BOTTLE_FIELDS})
        self.assertTrue(from_fields["success"], from_fields)
        self.assertEqual(from_fields["csv"], BOTTLE_CSV)
        self.assertTrue(from_fields["steps"][0]["hex"].startswith("1B4F45"))

        from_csv = self._print({"action": "push_fifo_fields", "csv": BOTTLE_CSV})
        self.assertTrue(from_csv["success"], from_csv)

        alias = self._print({"action": "send_fifo_data", "data": BOTTLE_CSV})
        self.assertTrue(alias["success"], alias)
        self.assertEqual(alias["csv"], BOTTLE_CSV)

    def test_soft_stop_resume(self):
        stop = self._print({"action": "soft_stop"})
        self.assertTrue(stop["success"], stop)
        self.assertFalse(self.fake.state.head_enabled)
        resume = self._print({"action": "soft_resume"})
        self.assertTrue(resume["success"], resume)
        self.assertEqual(stop["steps"][0]["hex"], "1B51314E04")
        self.assertEqual(resume["steps"][0]["hex"], "1B51315904")
        self.assertTrue(self.fake.state.head_enabled)

    def test_get_print_count_t1_t2(self):
        body = self._print({"action": "get_print_count"})
        self.assertTrue(body["success"], body)
        self.assertEqual(body["t1"], 304641327)
        self.assertEqual(body["t2"], 138)

    def test_erp_path_never_sends_print_go(self):
        self._print({"action": "put_named_label_online", "label_name": LABEL_NAME})
        self._print({"action": "query_online_label"})
        self._print({"action": "push_fifo_fields", "fields": BOTTLE_FIELDS, "csv": BOTTLE_CSV})
        self._print({"action": "push_fifo_fields", "fields": ["96.00", "KFBNIKHIL8", "11/08/2026", "10/05/2027"]})
        self._print({"action": "soft_stop"})
        self._print({"action": "soft_resume"})
        self.assertTrue(self.fake.sent)
        for packet in self.fake.sent:
            self.assertFalse(
                codenet.is_print_go_packet(packet),
                f"unexpected Print Go: {packet.hex().upper()}",
            )


class ErpHttpSmokeTests(unittest.TestCase):
    """8-step smoke over HTTP against the in-process mock — not 192.168.1.40."""

    def setUp(self):
        try:
            from flask import Flask
            from app.api.routes import api
            from app.core.bootstrap import AppContext
        except ImportError:
            self.skipTest("Flask not installed")

        self.svc, self.fake = _service_with_fake()
        self.ctx = AppContext(settings=Settings(api_key=None), print_service=self.svc)
        self.app = Flask(__name__)
        self.app.register_blueprint(api)
        self.client = self.app.test_client()
        self._ctx_patch = patch("app.api.routes.get_context", return_value=self.ctx)
        self._ctx_patch.start()

    def tearDown(self):
        patcher = getattr(self, "_ctx_patch", None)
        if patcher:
            patcher.stop()

    def _print(self, payload):
        body = {
            "printer_id": ERP_PRINTER_ID,
            "printer": {"ip": "192.168.1.40", "port": 7000},
            **payload,
        }
        return self.client.post("/print", json=body)

    def test_eight_step_photocell_path(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "healthy")

        identify = self._print({"action": "identify"})
        status = self._print({"action": "get_status"})
        self.assertEqual(identify.status_code, 200, identify.get_json())
        self.assertEqual(status.status_code, 200, status.get_json())
        self.assertTrue(identify.get_json()["success"])
        self.assertTrue(status.get_json()["success"])

        seq = self._print({"action": "sequence_on"})
        self.assertEqual(seq.status_code, 200, seq.get_json())
        self.assertTrue(seq.get_json()["success"])
        resume = self._print({"action": "soft_resume"})
        self.assertEqual(resume.status_code, 200, resume.get_json())
        self.assertTrue(resume.get_json()["success"])

        online = self._print({"action": "put_named_label_online", "label_name": LABEL_NAME})
        self.assertEqual(online.status_code, 200, online.get_json())
        self.assertTrue(online.get_json()["success"])

        query = self._print({"action": "query_online_label"})
        self.assertEqual(query.status_code, 200, query.get_json())
        self.assertEqual(query.get_json()["online_label"], "NOI")

        first = self._print({"action": "push_fifo_fields", "fields": BOTTLE_FIELDS, "csv": BOTTLE_CSV})
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertEqual(first.get_json()["csv"], BOTTLE_CSV)

        second = self._print(
            {
                "action": "push_fifo_fields",
                "fields": ["96.00", "KFBNIKHIL8", "12/08/2026", "10/05/2027"],
            }
        )
        self.assertEqual(second.status_code, 200, second.get_json())

        stop = self._print({"action": "soft_stop"})
        resume = self._print({"action": "soft_resume"})
        self.assertEqual(stop.status_code, 200, stop.get_json())
        self.assertEqual(resume.status_code, 200, resume.get_json())
        self.assertTrue(self.fake.state.head_enabled)

        for packet in self.fake.sent:
            self.assertFalse(codenet.is_print_go_packet(packet), packet.hex().upper())
            self.assertFalse(packet[1:2] == b"}", packet.hex().upper())


if __name__ == "__main__":
    unittest.main()
