"""Entry point for ``python -m capsqual`` / ``python -m CapsQual``."""
import sys
from pathlib import Path

# Ensure the package directory is on sys.path so sibling imports
# (e.g. ``from transcript import Transcript``) work regardless of
# whether the user runs ``python -m capsqual`` or ``python -m CapsQual``.
_pkg_dir = str(Path(__file__).resolve().parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from cli import main

if __name__ == "__main__":
    sys.exit(main())
