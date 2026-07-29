"""CapsQual entry point."""
import sys
import os

from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from utils import resource_path, logger
from editor import SRTEditor


def main():
    app = QApplication(sys.argv)

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

    # Finish splash and show main window
    if splash:
        splash.finish(editor)
    editor.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
