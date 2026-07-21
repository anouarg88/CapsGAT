"""Shared utilities for CapsQual."""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resource_path(relative_path):
    """Return the absolute path to a resource (works for PyInstaller bundles).

    Uses the directory of this file (utils.py) as the anchor, so it works
    regardless of the current working directory — whether CapsQual is
    launched via ``python main.py``, ``python -m CapsQual``, or as a
    PyInstaller bundle.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)
