import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.app import create_app
from src.core.config import Settings


def test_start_and_health(tmp_path):
    config = Settings(internal_api_key="test-service-key-1234", storage_root=tmp_path)
    with TestClient(create_app(config)) as client:
        for path in ["/health", "/health/live", "/health/ready"]:
            assert client.get(path).status_code == 200
        assert client.get("/api/v1/metrics").status_code == 401


def test_invalid_settings():
    with pytest.raises(ValidationError):
        Settings(internal_api_key="short")
