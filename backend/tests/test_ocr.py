import pytest

from app.adapters.ocr import parse_tesseract_tsv


def test_tesseract_tsv_parser_returns_lines_and_normalized_confidence() -> None:
    payload = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t90.0\tVitamin",
            "5\t1\t1\t1\t1\t2\t45\t20\t20\t12\t80.0\tC",
        ]
    )

    result = parse_tesseract_tsv(payload, "eng")

    assert result.text == "Vitamin C"
    assert result.confidence == pytest.approx(0.85)
    assert result.lines[0].width == 55
