import json

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from src.api.app import create_app
from src.core.config import Settings
from src.core.runtime import ServiceError, digest
from src.storage.objects import LocalStore, S3Store, safe_key
from tests.fixtures.documents import NATIVE, pdf

KEY = "tenant/acme/documents/report/versions/v1/original/report.pdf"
AUTH = {"X-Internal-Key": "test-service-key-1234"}


def config(tmp_path, **kwargs):
    return Settings(internal_api_key=AUTH["X-Internal-Key"], storage_root=tmp_path, **kwargs)


def request_data(stages):
    return {
        "tenant_id": "acme",
        "document_id": "report",
        "document_version_id": "v1",
        "source": {"key": KEY, "mime_type": "application/pdf"},
        "stages": stages,
    }


def seed(tmp_path):
    cfg = config(tmp_path)
    path = LocalStore(cfg).path(KEY)
    path.parent.mkdir(parents=True)
    path.write_bytes(pdf(("native", "scanned", "table")))
    return cfg


def test_s3_pipeline_and_idempotency(tmp_path):
    with mock_aws():
        cfg = config(
            tmp_path,
            storage_backend="s3",
            storage_bucket="docs",
            storage_access_key="test",
            storage_secret_key="test",
        )
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="docs")
        data = pdf(("native", "scanned", "table"))
        s3.put_object(Bucket="docs", Key=KEY, Body=data)
        req = request_data(["render", "chunks"])
        with TestClient(create_app(cfg)) as client:
            response = client.post("/api/v1/process", json=req, headers=AUTH)
            m = response.json()
            assert response.status_code == 200 and m["status"] == "success", m
            assert m["source_sha256"] == digest(data) and m["classification"] == "mixed"
            assert client.post("/api/v1/process", json=req, headers=AUTH).json() == m
            store = S3Store(cfg)
            for p in m["pages"]:
                ref = p["artifacts"]["chunks"]
                content = store.read(ref["key"], ref["size"])
                assert digest(content) == ref["sha256"]
                assert json.loads(content)["chunks"][0]["page_number"] == p["page_number"]
            assert store.exists(m["manifest_key"]) and "Signature" in store.signed_url(m["manifest_key"])
            assert store.read(KEY, len(data)) == data
            with pytest.raises(ServiceError):
                store.delete(KEY)


def test_recover_single_page(tmp_path, monkeypatch):
    cfg = seed(tmp_path)
    from src.ingestion import parsers

    original = parsers.recognize

    def fail(*args):
        raise ServiceError("ocr_timeout", "Timeout", "ocr", 503, True)

    monkeypatch.setattr(parsers, "recognize", fail)
    req = request_data(["chunks", "render"])
    with TestClient(create_app(cfg)) as client:
        first = client.post("/api/v1/process", json=req, headers=AUTH).json()
        assert first["status"] == "partial" and first["failed_pages"] == [2]
        monkeypatch.setattr(parsers, "recognize", original)
        retry = client.post("/api/v1/process", json=req, headers=AUTH).json()
        assert retry["status"] == "success" and retry["processing_run_id"] == first["processing_run_id"]
        assert retry["pages"][0]["stages"]["extraction"] == "cached"
        assert retry["pages"][1]["stages"]["extraction"] == "success"
        assert retry["pages"][0]["artifacts"] == first["pages"][0]["artifacts"]


def test_api_extraction_scope_limits(tmp_path):
    cfg = seed(tmp_path)
    with TestClient(create_app(cfg)) as client:
        req = request_data(["extraction"])
        req["pages"] = [1]
        for kind in ("text", "tables", "layout", "ocr"):
            resp = client.post("/api/v1/extraction/" + kind, headers=AUTH, json=req)
            assert resp.status_code == 200 and resp.json()["pages"][0]["page_number"] == 1
            if kind == "text":
                assert resp.json()["pages"][0]["text"] == NATIVE
        req["source"]["key"] = KEY.replace("/acme/", "/other/")
        assert client.post("/api/v1/process", headers=AUTH, json=req).status_code == 422
        assert (
            client.post(
                "/api/v1/process", headers=AUTH, content=b"a" * (cfg.max_request_bytes + 1)
            ).status_code
            == 413
        )
        assert client.get("/api/v1/models/text/status", headers=AUTH).json()["state"] == "unloaded"


@pytest.mark.parametrize(
    "key", ["../secret", "x//z", "https://example.com/a", "tenant/a/../z", "x/CON.doc", "x/a\\b"]
)
def test_unsafe_keys(key):
    with pytest.raises(ServiceError):
        safe_key(key)
