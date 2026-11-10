import pytest

from src.core.config import Settings
from src.core.runtime import ServiceError
from src.ingestion.parsers import open_document
from src.schemas.contracts import Source
from tests.fixtures.documents import NATIVE, pdf, scan


def parse(data, mime, ext):
    source = Source(key="original." + ext, mime_type=mime)
    cfg = Settings(internal_api_key="test-service-key-1234")
    with open_document(data, source, cfg) as doc:
        output = []
        for i in range(doc.count):
            with doc.render(i) as im:
                assert max(im.size) <= cfg.max_image_side
                output.append(doc.extract(i, f"page-{i + 1}", False, lambda: im))
        return output


def test_real_pdf_ocr_tables_and_layout():
    pages = parse(
        pdf(("native", "scanned", "mixed", "table", "chart", "columns")), "application/pdf", "pdf"
    )
    assert pages[0].text == NATIVE and pages[0].extraction_method == "native"
    for i in (1, 2):
        assert "fifty monitors" in pages[i].text.lower()
        assert pages[i].page_number == i + 1
    assert pages[2].classification == "mixed" and NATIVE in pages[2].text
    assert pages[3].tables[0].rows[1] == ["Finance", "5000"]
    assert any(e.kind == "caption" for e in pages[4].elements)
    assert any(e.text == "Right column" for e in pages[5].elements)


@pytest.mark.parametrize("fmt,mime,ext", [("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg")])
def test_real_image_ocr(fmt, mime, ext):
    assert "Warehouse" in parse(scan(fmt), mime, ext)[0].text


@pytest.mark.parametrize(
    "data,ext", [(b"", "pdf"), (b"%PDF-1.5 broken", "pdf"), (b"bad", "pdf"), (pdf(), "png")]
)
def test_invalid_files(data, ext):
    with pytest.raises(ServiceError):
        parse(data, "application/pdf", ext)
