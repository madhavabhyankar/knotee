import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Knotee")
    app.setOrganizationName("Knotee")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    # macOS: don't quit when last window is closed via ⌘W
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
