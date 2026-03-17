"""Shared utilities for CapsQual."""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resource_path(relative_path):
    """Return the absolute path to a resource (works for PyInstaller bundles)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
