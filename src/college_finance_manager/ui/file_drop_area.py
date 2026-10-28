from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class FileDropArea(QFrame):
    """Accept local file copies; actual attachment checks stay in the import use case."""

    files_dropped = Signal(list)

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fileDropArea")
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        self.caption = QLabel(caption)
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        hint = QLabel("支持 JPG / PNG / PDF · 每个不超过 20 MB · 可多选")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.caption)
        layout.addWidget(hint)

    @staticmethod
    def _paths(mime_data) -> list[Path]:
        if not mime_data.hasUrls():
            return []
        paths = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                return []
            path = Path(url.toLocalFile())
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".pdf"}:
                return []
            resolved = path.resolve()
            if resolved not in paths:
                paths.append(resolved)
        return paths

    def _highlight(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event) -> None:
        if self._paths(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self._highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._paths(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._highlight(False)
        event.accept()

    def dropEvent(self, event) -> None:
        self._highlight(False)
        paths = self._paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.files_dropped.emit(paths)
