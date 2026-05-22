"""Shared product constants for the TColorRamp Nuke plugin."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_PATH = Path(__file__).resolve().parent
INSTALLATION_PATH = str(PACKAGE_PATH)

PRODUCT_NAME = "TColorRamp"
PRODUCT_VERSION = "1.0"
PRODUCT_RELEASE_YEAR = "2026"
PRODUCT_VENDOR = "Thomas Petroni"
PRODUCT_VENDOR_URL = "https://www.linkedin.com/in/thomas-petroni/"

NODE_CLASS_NAME = PRODUCT_NAME
MENU_NAME = PRODUCT_NAME
PLUGIN_BIN_DIRECTORY = "bin"

PLUGIN_LOADED_ENV_VAR = "TCOLORRAMP_LOADED"
PLUGIN_BINARY_PATH_ENV_VAR = "TCOLORRAMP_PLUGIN_BIN_PATH"


def normalized_path(path: str) -> str:
    """Normalize a filesystem path for Nuke plugin registration."""
    return path.replace(os.sep, "/")
