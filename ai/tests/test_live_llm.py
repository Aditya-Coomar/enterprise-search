"""Run with a local or explicitly configured provider using only synthetic input."""

import os

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.test_pipeline import AUTH, config


def test_live_knowledge(tmp_path):
    if os.environ.get("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 and configure a provider")
    cfg = config(tmp_path)
    text = "Project Mercury was approved by Ada Patel."
    payload = {
        "tenant_id": "test",
        "document_id": "minutes",
        "document_version_id": "v1",
        "page_number": 1,
        "chunk_id": "approval",
        "text": text,
    }
    with TestClient(create_app(cfg)) as api:
        for route in ["entities", "relationships"]:
            response = api.post("/api/v1/" + route + "/extract", json=payload, headers=AUTH)
            assert response.status_code == 200, response.json()
            values = response.json()["candidates"]
            assert values and all(v["evidence"] in text and v["chunk_id"] == "approval" for v in values)
            if route == "relationships":
                assert any(
                    v["relationship_type"] == "APPROVED_BY"
                    and "Mercury" in v["source"]
                    and "Ada" in v["target"]
                    for v in values
                ), values
