"""Shared utilities for CapsQual."""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


#: Name of the per-user data directory used for files CapsQual creates at
#: runtime (e.g. custom symbols). Never write into the install directory —
#: it may be read-only (Program Files) or read-only inside a bundle.
APP_NAME = "CapsQual"


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


def app_data_dir():
    """Return the platform-conformant writable directory for CapsQual user data.

    Follows each OS's convention for per-user application data:

    - Windows: ``%APPDATA%\\CapsQual`` (e.g. ``C:\\Users\\<user>\\AppData\\Roaming\\CapsQual``)
    - macOS:   ``~/Library/Application Support/CapsQual``
    - Linux:   ``$XDG_DATA_HOME/CapsQual`` or ``~/.local/share/CapsQual``

    The directory is created on demand. This is the correct home for files
    CapsQual writes at runtime (``custom_symbols.json``, ...) — the install
    directory must never be used for writable data.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    else:  # Linux and other Unix-likes
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        # Do not crash at import time if the standard location is not
        # writable; save_custom_symbols() surfaces a friendly error later.
        logger.warning("Could not create data directory %s", path)
    return path
