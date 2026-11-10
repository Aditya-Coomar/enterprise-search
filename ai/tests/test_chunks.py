import pytest

from src.chunking.splitter import chunk_page, normalize
from src.core.config import Settings
from src.schemas.contracts import Context
from tests.fixtures.documents import pdf
from tests.test_ingestion import parse


@pytest.mark.parametrize("strategy", ["heading", "fixed", "overlap", "paragraph", "page"])
def test_deterministic_offsets_and_atomic_tables(strategy):
    p = parse(pdf(("table",)), "application/pdf", "pdf")[0]
    c = Context(tenant_id="tenant", document_id="document", document_version_id="v")
    cfg = Settings(internal_api_key="test-service-key-1234", chunk_size=22, chunk_overlap=4)
    norm, items = chunk_page(c, p, "artifact", cfg, strategy, set())
    assert items and all(x.text == norm[x.start : x.end] and x.document_version_id == "v" for x in items)
    assert len([x for x in items if x.table_id]) == 1
    assert chunk_page(c, p, "artifact", cfg, strategy, set())[1] == items
    if strategy == "overlap":
        assert items[0].end - items[1].start == 4


def test_normalization():
    assert normalize("co\u00ad\noperate  now\x00\r\nA-B") == "cooperate now\nA-B"
