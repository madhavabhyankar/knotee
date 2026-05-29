from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QMessageBox,
)

from ..storage import db
from ..storage.models import Meeting


class HistoryView(QWidget):
    meeting_selected = Signal(int)   # meeting_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._meetings: list[Meeting] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel("Meetings")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { border: 1px solid #e5e7eb; border-radius: 6px; }"
            "QListWidget::item { padding: 10px 8px; border-bottom: 1px solid #f3f4f6; }"
            "QListWidget::item:selected { background: #ede9fe; color: black; }"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, stretch=1)

    def refresh(self) -> None:
        self._meetings = db.list_meetings()
        self._render(self._meetings)

    def _filter(self, text: str) -> None:
        lower = text.lower()
        filtered = [m for m in self._meetings if lower in m.title.lower()]
        self._render(filtered)

    def _render(self, meetings: list[Meeting]) -> None:
        self._list.clear()
        for m in meetings:
            date_str = m.started_at.strftime("%b %d, %Y %H:%M")
            duration = ""
            if m.ended_at:
                secs = int((m.ended_at - m.started_at).total_seconds())
                mins, s = divmod(secs, 60)
                duration = f"  ·  {mins}m {s:02d}s"
            item = QListWidgetItem(f"{m.title}\n{date_str}{duration}")
            item.setData(Qt.UserRole, m.id)
            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        mid = item.data(Qt.UserRole)
        self.meeting_selected.emit(mid)
