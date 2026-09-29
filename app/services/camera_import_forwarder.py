"""
Camera import_batch forwarder (aligned with Rynan printer-middleware).

On send_fifo_data / push_fifo_fields with camera_import.enabled, POST
{barcode, text} to the camera URL immediately (before Domino OE).

text = FIFO CSV (data / csv / fields[]). Print success is independent of camera.

ERP should check camera_import.erp_alert_recommended and send WhatsApp when
alert_reasons includes empty_barcode and/or camera_http_failure.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from app.utils.logger import log

DEFAULT_CAMERA_URL = os.getenv(
    "CAMERA_IMPORT_BATCH_URL",
    "http://192.168.0.68:5001/api/import_batch",
)
CAMERA_IMPORT_ENABLED = os.getenv("CAMERA_IMPORT_ENABLED", "true").lower() == "true"
CAMERA_IMPORT_TIMEOUT = float(os.getenv("CAMERA_IMPORT_TIMEOUT", "3"))

# Actions that may carry variable print text for the camera (Domino OE path).
CAMERA_FIFO_ACTIONS = frozenset({"send_fifo_data", "push_fifo_fields"})


def resolve_camera_target(request_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (url, barcode) when camera_import is enabled on the request."""
    if not CAMERA_IMPORT_ENABLED:
        return None, None

    inline = request_data.get("camera_import")
    if not isinstance(inline, dict) or not inline.get("enabled"):
        return None, None

    barcode = str(inline.get("barcode") or "").strip()
    url = str(inline.get("url") or DEFAULT_CAMERA_URL).strip()
    if not url:
        return None, None

    if not barcode:
        log(
            "Camera import barcode empty — ERP should alert (empty_barcode)",
            level="WARNING",
            camera_import_missing_barcode=True,
        )

    return url, barcode


def post_camera_import(url: str, barcode: str, text: str) -> Dict[str, Any]:
    payload = json.dumps({"barcode": barcode, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    result: Dict[str, Any] = {
        "ok": False,
        "url": url,
        "barcode": barcode,
        "text_length": len(text),
        "status_code": None,
        "reason": None,
    }

    try:
        with urllib.request.urlopen(req, timeout=CAMERA_IMPORT_TIMEOUT) as resp:
            result["status_code"] = resp.getcode()
            result["ok"] = 200 <= resp.getcode() < 300
            result["reason"] = "OK" if result["ok"] else f"HTTP {resp.getcode()}"
    except urllib.error.HTTPError as exc:
        result["status_code"] = exc.code
        result["reason"] = f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 — surface any camera transport failure to ERP meta
        result["reason"] = str(exc)

    return result


def forward_camera_import_immediate(
    job_id: str,
    request_data: Dict[str, Any],
    fifo_text: str,
    *,
    printer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync: POST camera before Domino OE.

    Does not raise; always returns meta for the /print response so ERP can
    WhatsApp on empty_barcode or camera_http_failure.
    """
    url, barcode = resolve_camera_target(request_data)
    meta: Dict[str, Any] = {
        "attempted": False,
        "flow": "immediate",
        "camera_ok": False,
        "url": url,
        "barcode": barcode if barcode is not None else "",
        "missing_barcode": False,
        "erp_alert_recommended": False,
        "alert_reasons": [],
        "status": "skipped",
        "reason": None,
        "text_source": "fifo_data",
        "text_length": 0,
    }

    if url is None:
        meta["reason"] = "camera_import not enabled"
        return meta

    missing_barcode = not bool(barcode)
    meta["missing_barcode"] = missing_barcode
    meta["attempted"] = True

    if missing_barcode:
        meta["alert_reasons"].append("empty_barcode")
        meta["erp_alert_recommended"] = True

    text = str(fifo_text or "")
    meta["text_length"] = len(text)

    if not text:
        meta["status"] = "no_text"
        meta["reason"] = "no FIFO text available for camera"
        log(
            meta["reason"],
            level="ERROR",
            job_id=job_id,
            printer_id=printer_id,
            camera_import=meta,
        )
        return meta

    camera_result = post_camera_import(url, barcode or "", text)
    meta["camera"] = camera_result
    meta["camera_ok"] = bool(camera_result.get("ok"))
    meta["status"] = "sent" if camera_result.get("ok") else "camera_failed"
    meta["reason"] = camera_result.get("reason")

    if not camera_result.get("ok"):
        meta["alert_reasons"].append("camera_http_failure")
        meta["erp_alert_recommended"] = True

    level = "INFO" if camera_result.get("ok") else "ERROR"
    alerts = ",".join(meta["alert_reasons"]) if meta["alert_reasons"] else ""
    log(
        (
            f"Immediate camera import "
            f"{'succeeded' if camera_result.get('ok') else 'failed'} "
            f"barcode={barcode or '(empty)'} text_len={len(text)} url={url}"
            f"{' alerts=' + alerts if alerts else ''}"
        ),
        level=level,
        job_id=job_id,
        printer_id=printer_id,
        camera_import=meta,
    )
    return meta
