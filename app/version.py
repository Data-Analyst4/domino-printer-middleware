"""Domino middleware version info."""

VERSION = "1.1.0"
BUILD = "domino-codenet"


def get_version_info() -> dict:
    return {
        "version": VERSION,
        "build": BUILD,
        "service": "domino-printer-middleware",
        "protocol": "domino_ax_codenet",
        "features": [
            "Optional camera_import on send_fifo_data / push_fifo_fields (immediate, before OE)",
            "Camera URL from CAMERA_IMPORT_BATCH_URL or per-request camera_import.url",
        ],
    }
