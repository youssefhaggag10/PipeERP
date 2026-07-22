import os

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip("GUI smoke tests run in the dedicated offscreen workflow", allow_module_level=True)


def _order() -> dict:
    return {
        "order_number": "MO-WIZARD",
        "planned_batches": 10,
        "actual_batches": 10,
        "materials": [
            {
                "product_id": 1,
                "code": "RAW-A",
                "name": "خامة أ",
                "quantity_per_batch": 200,
                "actual_quantity": 2000,
                "unit_cost": 2,
            },
            {
                "product_id": 2,
                "code": "RAW-X",
                "name": "خامة X",
                "quantity_per_batch": 100,
                "actual_quantity": 1000,
                "unit_cost": 5,
            },
        ],
        "outputs": [
            {
                "product_id": 3,
                "code": "FG-28",
                "name": "ماسورة 28",
                "planned_quantity": 100,
                "standard_weight_kg": 28,
            }
        ],
    }


def test_completion_wizard_skips_adjustments_for_full_batches() -> None:
    from PySide6.QtWidgets import QApplication, QWizard

    from app.ui.production_completion_wizard import ProductionCompletionWizard

    app = QApplication.instance() or QApplication([])
    wizard = ProductionCompletionWizard(_order())
    wizard.show()
    app.processEvents()

    assert wizard.currentId() == wizard.PRODUCTION_PAGE
    assert wizard.all_complete_radio.isChecked()
    assert wizard.nextId() == wizard.SUMMARY_PAGE
    assert wizard.adjustments_table.rowCount() == 0
    assert (
        wizard.button(QWizard.WizardButton.FinishButton).text()
        == "إتمام الأمر واستلام الإنتاج"
    )

    wizard.close()
    app.processEvents()


def test_completion_wizard_groups_three_modified_batches_and_calculates_return() -> None:
    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

    from app.ui.production_completion_wizard import ProductionCompletionWizard

    app = QApplication.instance() or QApplication([])
    wizard = ProductionCompletionWizard(_order())
    wizard.show()
    app.processEvents()
    wizard.modified_radio.setChecked(True)
    wizard.add_adjustment_row()

    batch_input = wizard.adjustments_table.cellWidget(0, 0)
    material_input = wizard.adjustments_table.cellWidget(0, 1)
    reason_input = wizard.adjustments_table.cellWidget(0, 2)
    assert isinstance(batch_input, QLineEdit)
    assert isinstance(material_input, QComboBox)
    assert isinstance(reason_input, QLineEdit)

    batch_input.setText("3")
    material_input.setCurrentIndex(material_input.findData(2))
    reason_input.setText("تسببت في عيب بالإنتاج")

    good, defective, actual_weight = wizard.output_inputs[3]
    good.setText("95")
    defective.setText("5")
    actual_weight.setText("2660")
    wizard.scrap_input.setText("40")

    values = wizard.values()
    preview = wizard.preview()

    assert values["actual_batches"] == 10
    assert values["full_batches"] == 7
    assert values["modified_batches"] == 3
    assert len(values["adjustments"]) == 1
    assert preview["full_mix_cost"] == pytest.approx(6300)
    assert preview["modified_mix_cost"] == pytest.approx(1200)
    assert preview["total_cost"] == pytest.approx(7500)
    raw_x = next(row for row in preview["materials"] if row["product_id"] == 2)
    assert raw_x["issued"] == pytest.approx(1000)
    assert raw_x["used"] == pytest.approx(700)
    assert raw_x["unused"] == pytest.approx(300)

    wizard.close()
    app.processEvents()


def test_final_wizard_removes_defective_output_and_recalculates_scrap() -> None:
    from PySide6.QtWidgets import QApplication

    from app.ui.final_production_completion_wizard import FinalProductionCompletionWizard

    app = QApplication.instance() or QApplication([])
    wizard = FinalProductionCompletionWizard(_order())
    wizard.show()
    app.processEvents()

    assert wizard.outputs_table.isColumnHidden(2)
    good, defective, actual_weight = wizard.output_inputs[3]
    assert defective.text() == "0"
    assert defective.isReadOnly()
    assert wizard.summary_labels["defective_output_quantity"].isHidden()
    assert float(wizard.scrap_input.text()) == pytest.approx(200)

    good.setText("90")
    app.processEvents()
    assert float(actual_weight.text()) == pytest.approx(2520)
    assert float(wizard.scrap_input.text()) == pytest.approx(480)

    wizard.actual_batches_input.setText("9")
    app.processEvents()
    assert float(wizard.scrap_input.text()) == pytest.approx(180)

    wizard.actual_batches_input.setText("11")
    app.processEvents()
    assert float(wizard.scrap_input.text()) == pytest.approx(780)

    wizard.close()
    app.processEvents()
