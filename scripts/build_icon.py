"""Generate the Windows ICO from the application's vector drawing."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from college_finance_manager.ui.app_icon import create_app_icon


def main() -> None:
    app = QApplication.instance() or QApplication([])
    icon = create_app_icon()
    sizes = (16, 24, 32, 48, 64, 128, 256)
    offset = 6 + 16 * len(sizes)
    entries, images = [], []
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not icon.pixmap(size, size).save(buffer, "PNG"):
            raise RuntimeError("Unable to encode icon")
        data = bytes(buffer.data())
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        images.append(data)
        offset += len(data)
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + images))


if __name__ == "__main__":
    main()
