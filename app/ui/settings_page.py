from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.repositories.print_settings_repository import PrintSettingsRepository


class SettingsPage(QWidget):
    def __init__(self, repository: PrintSettingsRepository) -> None:
        super().__init__()
        self.repository = repository
        self.logo_source: str | None = None
        self.qr_source: str | None = None
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الإعدادات")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "بيانات فاتورة المبيعات والطابعة الحرارية والهوية التي تظهر على كل نسخة مطبوعة"
        )
        subtitle.setObjectName("subtitleLabel")

        self.company_name_input = QLineEdit()
        self.address_input = QLineEdit()
        self.phones_input = QPlainTextEdit()
        self.phones_input.setPlaceholderText("رقم هاتف في كل سطر")
        self.phones_input.setFixedHeight(72)
        self.footer_input = QPlainTextEdit()
        self.footer_input.setFixedHeight(64)
        self.beneficiary_input = QLineEdit()
        self.instapay_input = QLineEdit()
        self.instapay_input.setLayoutDirection(Qt.LeftToRight)

        invoice_group = QGroupBox("رأس وتذييل فاتورة المبيعات")
        invoice_form = QFormLayout(invoice_group)
        invoice_form.addRow("اسم المصنع", self.company_name_input)
        invoice_form.addRow("العنوان", self.address_input)
        invoice_form.addRow("أرقام الهاتف", self.phones_input)
        invoice_form.addRow("نص أسفل الفاتورة", self.footer_input)

        self.printer_input = QComboBox()
        self.printer_input.setEditable(True)
        paper_width = QLineEdit("80 mm — مساحة الطباعة 72 mm")
        paper_width.setReadOnly(True)
        printer_group = QGroupBox("الطابعة الحرارية")
        printer_form = QFormLayout(printer_group)
        printer_form.addRow("الطابعة", self.printer_input)
        printer_form.addRow("مقاس الرول", paper_width)
        printer_note = QLabel(
            "الطباعة تتم عبر تعريف النظام للطابعة USB. ثبّت تعريف Star TSP100 على الجهاز."
        )
        printer_note.setObjectName("subtitleLabel")
        printer_note.setWordWrap(True)
        printer_form.addRow(printer_note)

        self.logo_preview = self._image_preview()
        self.qr_preview = self._image_preview()
        logo_button = QPushButton("اختيار لوجو جديد")
        logo_button.setObjectName("secondaryButton")
        logo_button.clicked.connect(self.choose_logo)
        qr_button = QPushButton("اختيار QR جديد")
        qr_button.setObjectName("secondaryButton")
        qr_button.clicked.connect(self.choose_qr)

        logo_widget = QWidget()
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.addWidget(self.logo_preview)
        logo_layout.addWidget(logo_button)
        logo_layout.addStretch()

        qr_widget = QWidget()
        qr_layout = QHBoxLayout(qr_widget)
        qr_layout.setContentsMargins(0, 0, 0, 0)
        qr_layout.addWidget(self.qr_preview)
        qr_layout.addWidget(qr_button)
        qr_layout.addStretch()

        payment_group = QGroupBox("الدفع عبر InstaPay")
        payment_form = QFormLayout(payment_group)
        payment_form.addRow("اسم المستفيد", self.beneficiary_input)
        payment_form.addRow("عنوان InstaPay", self.instapay_input)
        payment_form.addRow("اللوجو", logo_widget)
        payment_form.addRow("QR Code", qr_widget)

        save_button = QPushButton("حفظ إعدادات الطباعة")
        save_button.clicked.connect(self.save)
        reload_button = QPushButton("إلغاء التعديلات وإعادة التحميل")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self.reload)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reload_button)
        actions.addStretch()

        columns = QHBoxLayout()
        columns.addWidget(invoice_group, 2)
        columns.addWidget(printer_group, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(columns)
        layout.addWidget(payment_group)
        layout.addLayout(actions)
        layout.addStretch()
        self.reload()

    @staticmethod
    def _image_preview() -> QLabel:
        preview = QLabel("لا توجد صورة")
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedSize(220, 145)
        preview.setStyleSheet(
            "border: 1px solid #334155; background: white; color: #111827;"
        )
        return preview

    def reload(self) -> None:
        values = self.repository.get_settings()
        self.company_name_input.setText(values["company_name"])
        self.address_input.setText(values["address"])
        self.phones_input.setPlainText(values["phones"])
        self.footer_input.setPlainText(values["footer"])
        self.beneficiary_input.setText(values["beneficiary_name"])
        self.instapay_input.setText(values["instapay_handle"])
        self._reload_printers(values["printer_name"])
        self._set_preview(self.logo_preview, values["logo_path"])
        self._set_preview(self.qr_preview, values["qr_path"])
        self.logo_source = None
        self.qr_source = None

    def _reload_printers(self, configured_name: str) -> None:
        names = [printer.printerName() for printer in QPrinterInfo.availablePrinters()]
        if configured_name and configured_name not in names:
            names.insert(0, configured_name)
        self.printer_input.clear()
        self.printer_input.addItems(names or ["Star TSP100"])
        self.printer_input.setCurrentText(configured_name or "Star TSP100")

    def choose_logo(self) -> None:
        source = self._choose_image("اختيار لوجو الفاتورة")
        if source:
            self.logo_source = source
            self._set_preview(self.logo_preview, source)

    def choose_qr(self) -> None:
        source = self._choose_image("اختيار QR الخاص بـ InstaPay")
        if source:
            self.qr_source = source
            self._set_preview(self.qr_preview, source)

    def _choose_image(self, title: str) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        return path

    @staticmethod
    def _set_preview(label: QLabel, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText("تعذر عرض الصورة")
            return
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                label.width() - 8,
                label.height() - 8,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def save(self) -> None:
        try:
            self.repository.save_settings(
                {
                    "company_name": self.company_name_input.text(),
                    "address": self.address_input.text(),
                    "phones": self.phones_input.toPlainText(),
                    "footer": self.footer_input.toPlainText(),
                    "beneficiary_name": self.beneficiary_input.text(),
                    "instapay_handle": self.instapay_input.text(),
                    "printer_name": self.printer_input.currentText(),
                    "paper_width_mm": "80",
                },
                logo_source=self.logo_source,
                qr_source=self.qr_source,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم حفظ إعدادات الفاتورة والطباعة")
