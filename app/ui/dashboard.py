from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("الرئيسية"))
        layout.addWidget(QLabel("سيتم عرض مؤشرات المصنع هنا"))
        self.setLayout(layout)
