from pathlib import Path
from struct import unpack


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return unpack(">II", data[16:24])


def test_approved_invoice_background_is_portrait_a4_ratio() -> None:
    path = Path("app/assets/print/a4_invoice_background.png")

    assert path.is_file()
    width, height = _png_size(path)
    assert width >= 1000
    assert height >= 1400
    assert abs((width / height) - (210 / 297)) < 0.005
