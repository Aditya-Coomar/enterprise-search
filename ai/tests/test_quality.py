import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from scripts.evaluate_extraction import evaluate
from src.api.app import create_app
from src.extraction.layout import reading_order
from src.ingestion.parsers import open_document
from src.schemas.contracts import Element, Source
from tests.test_pipeline import AUTH, config, request_data, seed


def test_column_reading_order():
    elements = [
        Element(text=f"{side}{line}", kind="paragraph", bbox=(x, y, x + 40, y + 10))
        for line, y in [(1, 30), (2, 45)]
        for side, x in [("L", 10), ("R", 150)]
    ]
    assert [e.text for e in reading_order(elements, 250)] == ["L1", "L2", "R1", "R2"]


def test_exif_orientation(tmp_path):
    original = Image.new("RGB", (180, 90), "white")
    exif = original.getexif()
    exif[274] = 6
    with BytesIO() as stream:
        original.save(stream, format="JPEG", exif=exif)
        with (
            open_document(
                stream.getvalue(), Source(key="scan.jpg", mime_type="image/jpeg"), config(tmp_path)
            ) as doc,
            doc.render(0) as image,
        ):
            assert image.size == (90, 180)


def test_deleted_artifact_is_recreated(tmp_path):
    cfg = seed(tmp_path)
    with TestClient(create_app(cfg)) as api:
        req = request_data(["chunks"])
        req["pages"] = [1]
        m = api.post("/api/v1/process", json=req, headers=AUTH).json()
        key = m["pages"][0]["artifacts"]["chunks"]["key"]
        rt = api.app.state.runtime
        rt.store.delete(key)
        result = api.post("/api/v1/process", json=req, headers=AUTH).json()
        assert rt.store.exists(key) and result["pages"][0]["stages"]["chunks"] == "success"


def test_worker_emits_machine_readable_json(tmp_path, monkeypatch):
    cfg = seed(tmp_path)
    monkeypatch.setenv("INTERNAL_API_KEY", AUTH["X-Internal-Key"])
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(cfg.storage_root))
    req = request_data(["chunks"])
    source = tmp_path / "job.json"
    source.write_text(json.dumps(req), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "src.workers.processing_worker", str(source)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)["successful_pages"] == [1, 2, 3]


def test_evaluation():
    result = evaluate("One two three", "One two")
    assert result["wer"] == 1 / 3 and result["word_completeness"] == 2 / 3


def test_case_sensitive_tenant_storage(tmp_path):
    from src.storage.objects import LocalStore

    store = LocalStore(config(tmp_path))
    first = store.path("tenant/Alpha/documents/d/versions/v1/original/a.pdf")
    other = store.path("tenant/alpha/documents/d/versions/v1/original/a.pdf")
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"first")
    assert not other.exists()
