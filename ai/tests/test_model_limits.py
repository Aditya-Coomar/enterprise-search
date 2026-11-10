from threading import Event

import pytest

from src.core.config import Settings
from src.core.runtime import Metrics, ServiceError
from src.models.registry import Registry


def registry(**overrides):
    return Registry(Settings(internal_api_key="test-service-key-1234", **overrides), Metrics())


def test_timeout_retains_capacity_until_execution_finishes(monkeypatch):
    rt = registry(ai_inference_timeout_seconds=0.1)
    gate = Event()
    started = Event()

    def work(*args):
        started.set()
        gate.wait(5)
        return [], {}

    monkeypatch.setattr(rt, "_work", work)
    try:
        with pytest.raises(ServiceError, match="time budget"):
            rt.run("text", ["a"], "document")
        assert started.is_set()
        with pytest.raises(ServiceError, match="capacity"):
            rt.run("text", ["b"], "query")
    finally:
        gate.set()
        rt.close()


@pytest.mark.parametrize(
    "error", [NotImplementedError("MPS unsupported operation"), RuntimeError("CUDA out of memory")]
)
def test_device_error_reloads_on_cpu(monkeypatch, error):
    rt = registry()
    calls = []

    def load(name, slot, cpu=False):
        slot.model = object()
        slot.status = "ready"
        slot.device = "cpu" if cpu else "mps"
        calls.append(slot.device)

    def result(name, slot, inputs, mode):
        if slot.device != "cpu":
            raise error
        return [], slot.info()

    monkeypatch.setattr(rt, "_load", load)
    monkeypatch.setattr(rt, "_unload", lambda slot: setattr(slot, "model", None))
    monkeypatch.setattr(rt, "_result", result)
    try:
        assert rt.run("text", ["a"], "document")[1]["device"] == "cpu"
        assert calls == ["mps", "cpu"]
    finally:
        rt.close()
