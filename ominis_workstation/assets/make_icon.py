"""Render the workstation icon at every Windows size and pack an .ico."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen,
)
from PySide6.QtWidgets import QApplication

HERE = Path(__file__).resolve().parent
SIZES = (256, 128, 64, 48, 32, 24, 16)


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    scale = size / 256.0
    rect = QRectF(8 * scale, 8 * scale, 240 * scale, 240 * scale)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#1c3f78"))
    gradient.setColorAt(0.55, QColor("#0d1730"))
    gradient.setColorAt(1.0, QColor("#070d1b"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#2d5a9e"), max(1.0, 3 * scale)))
    painter.drawRoundedRect(rect, 52 * scale, 52 * scale)

    centre = QPointF(128 * scale, 128 * scale)
    # Radar rings.
    painter.setBrush(Qt.NoBrush)
    for radius, alpha in ((78, 150), (54, 190), (30, 230)):
        pen = QPen(QColor(88, 225, 255, alpha), max(1.0, 2.4 * scale))
        painter.setPen(pen)
        painter.drawEllipse(centre, radius * scale, radius * scale)

    # Sweep wedge.
    painter.setPen(Qt.NoPen)
    sweep = QColor("#58e1ff")
    sweep.setAlpha(80)
    painter.setBrush(sweep)
    painter.drawPie(
        QRectF(centre.x() - 78 * scale, centre.y() - 78 * scale,
               156 * scale, 156 * scale),
        30 * 16, 55 * 16)

    # Core and contact.
    painter.setBrush(QColor("#58e1ff"))
    painter.drawEllipse(centre, 13 * scale, 13 * scale)
    painter.setBrush(QColor("#ffb45c"))
    painter.drawEllipse(QPointF(centre.x() + 52 * scale,
                                centre.y() - 52 * scale),
                        9 * scale, 9 * scale)

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, images: dict[int, bytes]) -> None:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = b""
    payload = b""
    for size in sorted(images, reverse=True):
        blob = images[size]
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32,
                               len(blob), offset + len(payload))
        payload += blob
    path.write_bytes(header + entries + payload)


def chevron() -> QImage:
    image = QImage(24, 14, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor("#8fa3c8"), 2.4))
    painter.drawLine(QPointF(4, 4), QPointF(12, 11))
    painter.drawLine(QPointF(12, 11), QPointF(20, 4))
    painter.end()
    return image


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    images: dict[int, bytes] = {}
    for size in SIZES:
        image = draw(size)
        images[size] = png_bytes(image)
        if size == 256:
            (HERE / "icon.png").write_bytes(images[size])
    write_ico(HERE / "icon.ico", images)
    (HERE / "chevron.png").write_bytes(png_bytes(chevron()))
    print(f"wrote {HERE / 'icon.ico'} ({len(images)} sizes)")
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
