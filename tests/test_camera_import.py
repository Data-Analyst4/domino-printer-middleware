"""Camera import on FIFO actions — with and without camera_import block."""

from __future__ import annotations

import json
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
from app.services.printer_service import DominoPrintService  # noqa: E402
from mock_domino_printer import DemoPrinterState, build_response  # noqa: E402

ERP_PRINTER_ID = "DOMINO_AX_1"
BOTTLE_CSV = "95.00,KFBNIKHIL7,11/08/2026,10/05/2027"
CAMERA_URL = "http://127.0.0.1:9/api/import_batch"


class FakeDominoConnection:
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


class _FakeHttpResponse:
    def __init__(self, code: int = 200):
        self._code = code

    def getcode(self):
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b"{}"


def _service_with_fake():
    settings = Settings()
    svc = DominoPrintService(settings)
    cfg = PrinterConfig(printer_id=ERP_PRINTER_ID, ip="127.0.0.1", port=9)
    svc._printers = {ERP_PRINTER_ID: cfg}
    fake = FakeDominoConnection()
    svc._connections[ERP_PRINTER_ID] = fake
    svc._locks[ERP_PRINTER_ID] = threading.Lock()
    return svc, fake


class PlainFifoNoCameraTests(unittest.TestCase):
    def setUp(self):
        self.svc, self.fake = _service_with_fake()

    def test_plain_send_fifo_has_no_camera_import(self):
        result = self.svc.handle_print(
            {
                "printer_id": ERP_PRINTER_ID,
                "action": "send_fifo_data",
                "data": BOTTLE_CSV,
            }
        )
        self.assertTrue(result["success"])
        self.assertNotIn("camera_import", result)
        self.assertEqual(len(self.fake.sent), 1)

    def test_camera_disabled_block_skipped(self):
        result = self.svc.handle_print(
            {
                "printer_id": ERP_PRINTER_ID,
                "action": "send_fifo_data",
                "data": BOTTLE_CSV,
                "camera_import": {"enabled": False, "url": CAMERA_URL, "barcode": "123"},
            }
        )
        self.assertTrue(result["success"])
        self.assertNotIn("camera_import", result)


class CameraImportFifoTests(unittest.TestCase):
    def setUp(self):
        self.svc, self.fake = _service_with_fake()
        self.posted = []

    def _fake_urlopen(self, req, timeout=None):
        body = req.data.decode("utf-8") if isinstance(req.data, (bytes, bytearray)) else ""
        self.posted.append(
            {
                "url": req.full_url,
                "body": json.loads(body) if body else {},
                "timeout": timeout,
            }
        )
        return _FakeHttpResponse(200)

    def test_send_fifo_with_camera_posts_before_oe(self):
        with patch("app.services.camera_import_forwarder.urllib.request.urlopen", side_effect=self._fake_urlopen):
            result = self.svc.handle_print(
                {
                    "printer_id": ERP_PRINTER_ID,
                    "action": "send_fifo_data",
                    "data": BOTTLE_CSV,
                    "camera_import": {
                        "enabled": True,
                        "barcode": "8906164010577",
                        "url": CAMERA_URL,
                    },
                }
            )
        self.assertTrue(result["success"])
        self.assertIn("camera_import", result)
        cam = result["camera_import"]
        self.assertTrue(cam["camera_ok"])
        self.assertEqual(cam["status"], "sent")
        self.assertFalse(cam["erp_alert_recommended"])
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.posted[0]["url"], CAMERA_URL)
        self.assertEqual(
            self.posted[0]["body"],
            {"barcode": "8906164010577", "text": BOTTLE_CSV},
        )
        self.assertEqual(len(self.fake.sent), 1)

    def test_push_fifo_fields_alias_also_triggers_camera(self):
        with patch("app.services.camera_import_forwarder.urllib.request.urlopen", side_effect=self._fake_urlopen):
            result = self.svc.handle_print(
                {
                    "printer_id": ERP_PRINTER_ID,
                    "action": "push_fifo_fields",
                    "fields": ["A", "B"],
                    "camera_import": {
                        "enabled": True,
                        "barcode": "111",
                        "url": CAMERA_URL,
                    },
                }
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["camera_import"]["camera_ok"])
        self.assertEqual(self.posted[0]["body"]["text"], "A,B")

    def test_camera_http_failure_does_not_fail_print(self):
        def boom(req, timeout=None):
            raise OSError("camera down")

        with patch("app.services.camera_import_forwarder.urllib.request.urlopen", side_effect=boom):
            result = self.svc.handle_print(
                {
                    "printer_id": ERP_PRINTER_ID,
                    "action": "send_fifo_data",
                    "data": BOTTLE_CSV,
                    "camera_import": {
                        "enabled": True,
                        "barcode": "8906164010577",
                        "url": CAMERA_URL,
                    },
                }
            )
        self.assertTrue(result["success"])
        cam = result["camera_import"]
        self.assertFalse(cam["camera_ok"])
        self.assertTrue(cam["erp_alert_recommended"])
        self.assertIn("camera_http_failure", cam["alert_reasons"])
        self.assertEqual(len(self.fake.sent), 1)

    def test_identify_never_calls_camera(self):
        with patch("app.services.camera_import_forwarder.urllib.request.urlopen", side_effect=self._fake_urlopen):
            result = self.svc.handle_print(
                {
                    "printer_id": ERP_PRINTER_ID,
                    "action": "identify",
                    "camera_import": {
                        "enabled": True,
                        "barcode": "8906164010577",
                        "url": CAMERA_URL,
                    },
                }
            )
        self.assertTrue(result["success"])
        self.assertNotIn("camera_import", result)
        self.assertEqual(self.posted, [])


if __name__ == "__main__":
    unittest.main()
