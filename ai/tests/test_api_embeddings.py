import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from src.api.app import create_app
from src.embeddings.tensors import deserialize
from tests.test_pipeline import AUTH, request_data, seed


def test_artifact_and_contracts(tmp_path, monkeypatch):
    cfg = seed(tmp_path).model_copy(update={"colpali_batch_size": 2})
    with TestClient(create_app(cfg)) as api:
        rt = api.app.state.runtime
        calls = []

        def encode(name, inputs, mode):
            calls.append((name, len(inputs), mode))
            if name == "colpali" and mode == "document":
                assert all(isinstance(im, Image.Image) for im in inputs)
            shape = (7, 4) if name == "colpali" else (4,)
            return [np.ones(shape, dtype=np.float32) for _ in inputs], {
                "dimensions": 4,
                "model_id": name,
                "revision": "test",
            }

        monkeypatch.setattr(rt.models, "run", encode)
        req = request_data(["text_embeddings", "visual_embeddings"])
        result = api.post("/api/v1/process", json=req, headers=AUTH).json()
        assert result["status"] == "success"
        assert ("colpali", 2, "document") in calls
        for p in result["pages"]:
            ref = p["artifacts"]["visual_embeddings"]
            assert deserialize(
                rt.store.read(ref["key"], ref["size"]), ref["sha256"], ref["metadata"]["shape"]
            ).shape == (7, 4)
        passage = {
            "tenant_id": "acme",
            "document_id": "d",
            "document_version_id": "v",
            "page_number": 2,
            "chunk_id": "c",
            "text": "Evidence.",
        }
        for path, data in [
            ("text", passage),
            ("text/batch", {"items": [passage, passage]}),
            ("query", {"tenant_id": "acme", "text": "budget"}),
            ("visual/query", {"tenant_id": "acme", "text": "budget"}),
            ("visual/pages", req),
        ]:
            assert api.post("/api/v1/embeddings/" + path, json=data, headers=AUTH).status_code == 200
