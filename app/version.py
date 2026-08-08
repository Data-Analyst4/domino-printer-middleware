"""Domino middleware version info."""

VERSION = "1.0.0"
BUILD = "domino-codenet"


def get_version_info() -> dict:
    return {
        "version": VERSION,
        "build": BUILD,
        "service": "domino-printer-middleware",
        "protocol": "domino_ax_codenet",
    }
