from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.repositories.admin_repository import AdminRepository
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.ui.settings_page import SettingsPage
from app.utils.print_phone_utils import normalized_phone_numbers


class PrintSettingsPage(SettingsPage):
    watermark_settings_changed = Signal()

    def __init__(
        self,
        print_repository: PrintSettingsRepository,
        admin_repository: AdminRepository,
    ) -> None:
        self.print_repository = print_repository
        self._preserved_settings: dict[str, str] = {}
        self._watermark_source: str | None = None
        super().__init__(admin_repository)
        self.tabs.insertTab(0, self._build_print_tab(), "الطباعة")
        self.tabs.insertTab(1, self._build_watermark_tab(), "العلامة المائية")
        self.tabs.setCurrentIndex(0)
        self._reload_print_settings()

    def _build_print_tab(self) -> QWidget:
        tab = QWidget()

        self.company_name_input = QLineEdit()
        self.address_input = QLineEdit()
        self.phones_list = QListWidget()
        self.phones_list.setFixedHeight(145)
        self.phones_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.new_phone_input = QLineEdit()
        self.new_phone_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.new_phone_input.setPlaceholderText("اكتب رقم الهاتف الجديد")
        self.new_phone_input.returnPressed.connect(self._add_phone)

        add_phone_button = QPushButton("إضافة رقم")
        add_phone_button.clicked.connect(self._add_phone)
        remove_phone_button = QPushButton("حذف الرقم المحدد")
        remove_phone_button.setObjectName("secondaryButton")
        remove_phone_button.clicked.connect(self._remove_selected_phone)

        phone_actions = QHBoxLayout()
        phone_actions.addWidget(self.new_phone_input, 1)
        phone_actions.addWidget(add_phone_button)
        phone_actions.addWidget(remove_phone_button)

        phone_editor = QWidget()
        phone_layout = QVBoxLayout(phone_editor)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        phone_layout.addWidget(self.phones_list)
        phone_layout.addLayout(phone_actions)
        phone_note = QLabel(
            "الرقم الأول هو رقم الشركة الرئيسي، وباقي الأرقام تظهر تحت إدارة "
            "المبيعات. يمكنك سحب الأرقام لإعادة ترتيبها."
        )
        phone_note.setWordWrap(True)
        phone_note.setObjectName("subtitleLabel")
        phone_layout.addWidget(phone_note)

        invoice_group = QGroupBox("بيانات فاتورة المبيعات")
        invoice_form = QFormLayout(invoice_group)
        invoice_form.addRow("اسم المنشأة", self.company_name_input)
        invoice_form.addRow("العنوان", self.address_input)
        invoice_form.addRow("أرقام الشركة والمبيعات", phone_editor)

        self.printer_input = QComboBox()
        self.printer_input.setEditable(True)
        paper_size = QLineEdit("A4 — 210 × 297 مم — رأسي")
        paper_size.setReadOnly(True)

        printer_group = QGroupBox("طابعة فواتير A4")
        printer_form = QFormLayout(printer_group)
        printer_form.addRow("اسم الطابعة الافتراضية", self.printer_input)
        printer_form.addRow("المقاس", paper_size)
        printer_note = QLabel(
            "اختيار الطابعة هنا يحدد الطابعة الافتراضية عند فتح المعاينة. "
            "يمكن تغييره من نافذة الطباعة قبل إرسال الفاتورة."
        )
        printer_note.setWordWrap(True)
        printer_note.setObjectName("subtitleLabel")
        printer_form.addRow(printer_note)

        save_button = QPushButton("حفظ إعدادات الفاتورة")
        save_button.clicked.connect(self.save_print_settings)
        reload_button = QPushButton("إلغاء التعديلات وإعادة التحميل")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self._reload_print_settings)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reload_button)
        actions.addStretch()

        columns = QHBoxLayout()
        columns.addWidget(invoice_group, 2)
        columns.addWidget(printer_group, 1)

        layout = QVBoxLayout(tab)
        layout.addLayout(columns)
        layout.addLayout(actions)
        layout.addStretch()
        return tab

    def _build_watermark_tab(self) -> QWidget:
        tab = QWidget()
        self.watermark_enabled = QCheckBox("إظهار شعار 3A PIPES كعلامة مائية في كل الشاشات")

        self.watermark_path_label = QLineEdit()
        self.watermark_path_label.setReadOnly(True)
        self.watermark_path_label.setPlaceholderText("سيُستخدم شعار النظام الافتراضي")
        choose_button = QPushButton("اختيار صورة اللوجو")
        choose_button.clicked.connect(self._choose_watermark)
        clear_button = QPushButton("استخدام شعار النظام الافتراضي")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self._clear_watermark_source)

        image_actions = QHBoxLayout()
        image_actions.addWidget(self.watermark_path_label, 1)
        image_actions.addWidget(choose_button)
        image_actions.addWidget(clear_button)
        image_editor = QWidget()
        image_editor.setLayout(image_actions)

        self.watermark_opacity = QSpinBox()
        self.watermark_opacity.setRange(1, 40)
        self.watermark_opacity.setSuffix(" %")
        self.watermark_size = QSpinBox()
        self.watermark_size.setRange(10, 80)
        self.watermark_size.setSuffix(" % من مساحة الشاشة")

        group = QGroupBox("إعدادات العلامة المائية")
        form = QFormLayout(group)
        form.addRow("تشغيل", self.watermark_enabled)
        form.addRow("صورة العلامة", image_editor)
        form.addRow("الشفافية", self.watermark_opacity)
        form.addRow("الحجم", self.watermark_size)

        note = QLabel(
            "العلامة المائية تظهر في منتصف كل شاشة بطبقة شفافة ولا تمنع الضغط على "
            "الأزرار أو التعامل مع الجداول. يفضل استخدام PNG بخلفية شفافة."
        )
        note.setWordWrap(True)
        note.setObjectName("subtitleLabel")

        save_button = QPushButton("حفظ وتطبيق العلامة المائية")
        save_button.clicked.connect(self.save_watermark_settings)
        reload_button = QPushButton("إلغاء التعديلات وإعادة التحميل")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self._reload_print_settings)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reload_button)
        actions.addStretch()

        layout = QVBoxLayout(tab)
        layout.addWidget(group)
        layout.addWidget(note)
        layout.addLayout(actions)
        layout.addStretch()
        return tab

    def reload(self) -> None:
        super().reload()
        if hasattr(self, "company_name_input"):
            self._reload_print_settings()

    def _reload_print_settings(self) -> None:
        values = self.print_repository.get_settings()
        self._preserved_settings = dict(values)
        self.company_name_input.setText(values["company_name"])
        self.address_input.setText(values["address"])
        self.phones_list.clear()
        self.phones_list.addItems(normalized_phone_numbers(values["phones"]))
        self.new_phone_input.clear()
        self._reload_printers(values["printer_name"])

        self._watermark_source = None
        self.watermark_enabled.setChecked(values.get("watermark_enabled", "0") == "1")
        self.watermark_opacity.setValue(int(float(values.get("watermark_opacity", "8"))))
        self.watermark_size.setValue(int(float(values.get("watermark_size", "35"))))
        self.watermark_path_label.setText(values.get("watermark_path", ""))

    def _reload_printers(self, configured_name: str) -> None:
        names = [printer.printerName() for printer in QPrinterInfo.availablePrinters()]
        if configured_name and configured_name not in names:
            names.insert(0, configured_name)
        self.printer_input.clear()
        self.printer_input.addItems(names)
        if configured_name:
            self.printer_input.setCurrentText(configured_name)

    def _choose_watermark(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "اختيار صورة العلامة المائية",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        self._watermark_source = path
        self.watermark_path_label.setText(path)

    def _clear_watermark_source(self) -> None:
        self._watermark_source = None
        self.watermark_path_label.setText(
            str(self.print_repository.default_logo_path())
        )

    def _add_phone(self) -> None:
        phone = self.new_phone_input.text().strip()
        if not phone:
            return
        existing = {
            self.phones_list.item(index).text().strip() for index in range(self.phones_list.count())
        }
        if phone in existing:
            QMessageBox.information(self, "تنبيه", "رقم الهاتف موجود بالفعل")
            return
        self.phones_list.addItem(phone)
        self.new_phone_input.clear()
        self.new_phone_input.setFocus()

    def _remove_selected_phone(self) -> None:
        for item in self.phones_list.selectedItems():
            self.phones_list.takeItem(self.phones_list.row(item))

    def _phone_values(self) -> str:
        return "\n".join(
            self.phones_list.item(index).text().strip()
            for index in range(self.phones_list.count())
            if self.phones_list.item(index).text().strip()
        )

    def _current_values(self) -> dict[str, str]:
        values = dict(self._preserved_settings)
        values.update(
            {
                "company_name": self.company_name_input.text(),
                "address": self.address_input.text(),
                "phones": self._phone_values(),
                "footer": self._preserved_settings.get("footer", ""),
                "instapay_handle": self._preserved_settings.get("instapay_handle", ""),
                "printer_name": self.printer_input.currentText(),
                "paper_width_mm": self._preserved_settings.get("paper_width_mm", "80"),
                "watermark_enabled": "1" if self.watermark_enabled.isChecked() else "0",
                "watermark_opacity": str(self.watermark_opacity.value()),
                "watermark_size": str(self.watermark_size.value()),
            }
        )
        return values

    def save_print_settings(self) -> None:
        try:
            self.print_repository.save_settings(self._current_values())
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self._reload_print_settings()
        QMessageBox.information(self, "تم", "تم حفظ بيانات الفاتورة والطابعة")

    def save_watermark_settings(self) -> None:
        try:
            self.print_repository.save_settings(
                self._current_values(), watermark_source=self._watermark_source
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self._reload_print_settings()
        self.watermark_settings_changed.emit()
        QMessageBox.information(self, "تم", "تم حفظ وتطبيق العلامة المائية")


__all__ = ["PrintSettingsPage"]
