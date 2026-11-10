import json

import httpx
import pytest

from src.core.config import Settings
from src.core.runtime import ServiceError
from src.extraction.candidates import OpenAICompatible
from src.schemas.contracts import Passage


def test_recovery_and_evidence():
    cfg = Settings(
        internal_api_key="test-service-key-1234",
        llm_provider="openai-compatible",
        llm_endpoint="https://llm.test/v1",
        llm_model="test",
        llm_retries=1,
    )
    p = Passage(
        tenant_id="t",
        document_id="d",
        document_version_id="v",
        chunk_id="c",
        page_number=4,
        text="Ada approved Mercury.",
    )
    valid = {
        "entities": [{"entity_type": "person", "name": "Ada", "evidence": p.text, "confidence": 0.9}],
        "relationships": [
            {
                "source": "Mercury",
                "target": "Ada",
                "relationship_type": "APPROVED_BY",
                "evidence": p.text,
                "confidence": 0.8,
            }
        ],
    }
    replies = iter(["{}", json.dumps(valid)])

    def call(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    with httpx.Client(transport=httpx.MockTransport(call)) as client:
        result = OpenAICompatible(cfg, client).extract(p)
    assert (
        result["relationships"][0]["page_number"] == 4
        and result["entities"][0]["normalized_name"] == "ada"
    )
    valid["entities"][0]["evidence"] = "invented"
    replies = iter([json.dumps(valid)])
    with (
        httpx.Client(transport=httpx.MockTransport(call)) as client,
        pytest.raises(ServiceError, match="evidence"),
    ):
        OpenAICompatible(cfg.model_copy(update={"llm_retries": 0}), client).extract(p)
