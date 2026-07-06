from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.RightToLeft)
        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        description_label = QLabel(description)
        description_label.setObjectName("subtitleLabel")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addStretch()
        self.setLayout(layout)
