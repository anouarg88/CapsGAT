"""CapsQual entry point."""
import sys
import os

from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QPixmap

from utils import resource_path, logger
from editor import SRTEditor


class _CapsQualApplication(QApplication):
    """QApplication subclass that catches macOS ``QFileOpenEvent``.

    On macOS, "Open With" and Dock-drop deliver file paths via Apple Events,
    which Qt translates into :class:`QFileOpenEvent` instances posted to the
    application object.  We intercept them here and store the paths so
    ``main()`` can forward them to the editor after initialisation.

    On Windows and Linux, ``QEvent.FileOpen`` is never fired, so this
    subclass is a harmless no-op on those platforms.
    """

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.open_event_paths: list[str] = []

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.FileOpen:          # QFileOpenEvent (macOS)
            path = e.url().toLocalFile()          # type: ignore[attr-defined]
            if path and os.path.exists(path):
                self.open_event_paths.append(os.path.abspath(path))
            return True
        return super().event(e)


def main():
    app = _CapsQualApplication(sys.argv)
    # ── Extract a file path from command-line arguments ──────────
    # Skips flag-like args (starting with "-") and the executable name.
    # This enables "Open With → CapsQual" and double-click file association
    # on Windows and Linux.
    startup_path: str | None = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and os.path.exists(arg):
            startup_path = os.path.abspath(arg)
            break


    splash = None
    splash_path = resource_path("images/splash.png")
    if os.path.exists(splash_path):
        splash_pix = QPixmap(splash_path)
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()
        splash.showMessage("Initializing CapsQual...", Qt.AlignBottom | Qt.AlignCenter, Qt.black)
        app.processEvents()
    else:
        logger.warning("Splash image not found, continuing without splash.")

    # Create main window (this should be fast now)
    editor = SRTEditor(splash)

    # Preload heavy modules while splash is still visible
    if splash:
        splash.showMessage("Loading modules...", Qt.AlignBottom | Qt.AlignCenter, Qt.black)
        app.processEvents()
    editor.preload_modules()   # this will take the time
    # ── Open file from command line (Windows/Linux) or
    #     Apple Event (macOS QFileOpenEvent) ─────────────────────
    path_to_open = startup_path
    if not path_to_open and app.open_event_paths:
        path_to_open = app.open_event_paths[0]
    if path_to_open:
        editor.open_recent_file(path_to_open)


    # Finish splash and show main window
    if splash:
        splash.finish(editor)
    editor.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
