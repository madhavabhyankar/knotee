import sys

# Guard: Knotee requires Python 3.11+ and the pyenv environment.
# Running inside another project's venv (e.g. AIProjects/lang) will pull in
# incompatible package versions. Use ./run.sh to launch with the right Python.
if sys.version_info < (3, 11) or "AIProjects" in sys.executable or "venv" in sys.executable:
    print(
        f"ERROR: Wrong Python: {sys.executable}\n"
        f"Run Knotee with:  ./run.sh\n"
        f"or:  /Users/madhavabhyankar/.pyenv/versions/3.13.12/bin/python3 main.py"
    )
    sys.exit(1)

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
