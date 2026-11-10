import os
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from src.core.config import Settings
from src.core.runtime import Metrics, ServiceError, digest
from src.embeddings.tensors import deserialize, serialize
from src.models.device import select
from src.models.registry import Registry


def test_device_selection():
    def backend(enabled):
        return SimpleNamespace(is_available=lambda: enabled)

    device = SimpleNamespace(cuda=backend(False), backends=SimpleNamespace(mps=backend(False)))
    assert select("auto", "auto", True, device) == ("cpu", False)
    assert select("auto", "cuda", True, device) == ("cpu", True)
    with pytest.raises(ServiceError):
        select("mps", "auto", False, device)
    device.backends.mps = backend(True)
    assert select("auto", "auto", True, device) == ("mps", False)
    device.cuda = backend(True)
    assert select("auto", "auto", True, device) == ("cuda", False)


def test_portable_tensor():
    tensor = np.arange(30, dtype=">f4").reshape(6, 5)
    data = serialize(tensor)
    assert np.array_equal(deserialize(data, digest(data), [6, 5]), tensor)
    with pytest.raises(ServiceError):
        deserialize(data, "0" * 64, [6, 5])


@pytest.mark.model
@pytest.mark.parametrize("name", ["text", "colpali"])
def test_real_cpu_inference(name):
    if os.getenv("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 after downloading pinned weights")
    cfg = Settings(
        internal_api_key="test-service-key-1234",
        ai_device="cpu",
        colpali_batch_size=2,
        ai_inference_timeout_seconds=600,
    )
    registry = Registry(cfg, Metrics())
    try:
        pages = (
            ["Revenue report", "Copper wire"]
            if name == "text"
            else [Image.new("RGB", (180, 100), color) for color in ("white", "black")]
        )
        docs, meta = registry.run(name, pages, "document")
        queries, _ = registry.run(name, ["Revenue"], "query")
        assert meta["device"] == "cpu" and all(np.isfinite(d).all() for d in docs)
        assert queries[0].shape[-1] == docs[0].shape[-1] and len(docs) == len(pages)
        if name == "colpali":
            assert docs[0].shape[0] > 100 and queries[0].shape[0] > 1
            data = serialize(docs[0])
            doc = deserialize(data, digest(data), list(docs[0].shape))
            assert np.isfinite((queries[0] @ doc.T).max(axis=1).sum())
        else:
            assert docs[0] @ queries[0] > docs[1] @ queries[0]
        print(name, docs[0].shape, queries[0].shape, meta["load_seconds"], meta["inference_seconds"])
    finally:
        registry.close()
    assert registry.status()[name]["state"] == "unloaded"
