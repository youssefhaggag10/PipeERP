from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class WatermarkOverlay(QWidget):
    """Transparent, click-through watermark displayed above all application pages."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._enabled = False
        self._opacity = 0.08
        self._size_percent = 35
        self._pixmap = QPixmap()

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.raise_()
        self.hide()

    def apply_settings(self, settings: dict[str, str]) -> None:
        enabled = str(settings.get("watermark_enabled", "0")).strip().lower()
        self._enabled = enabled in {"1", "true", "yes", "on"}
        try:
            opacity_percent = int(float(settings.get("watermark_opacity", "8")))
        except (TypeError, ValueError):
            opacity_percent = 8
        try:
            size_percent = int(float(settings.get("watermark_size", "35")))
        except (TypeError, ValueError):
            size_percent = 35

        self._opacity = max(0.01, min(0.40, opacity_percent / 100.0))
        self._size_percent = max(10, min(80, size_percent))

        path = Path(str(settings.get("watermark_path", ""))).expanduser()
        self._pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        visible = self._enabled and not self._pixmap.isNull()
        self.setVisible(visible)
        if visible:
            self.raise_()
        self.update()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        }:
            self.setGeometry(self.parentWidget().rect())
            self.raise_()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        if not self._enabled or self._pixmap.isNull():
            return
        available_width = max(1, self.width())
        available_height = max(1, self.height())
        target_width = max(80, int(available_width * self._size_percent / 100.0))
        target_height = max(80, int(available_height * self._size_percent / 100.0))
        scaled = self._pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (available_width - scaled.width()) // 2
        y = (available_height - scaled.height()) // 2
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(x, y, scaled)


__all__ = ["WatermarkOverlay"]
