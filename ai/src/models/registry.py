import gc
import platform
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass, field
from threading import BoundedSemaphore, Lock
from time import perf_counter
from typing import Any, Literal

import numpy as np
from PIL import Image

from src.core.config import Settings
from src.core.runtime import Metrics, ServiceError, log
from src.embeddings.tensors import validate_tensor
from src.models.device import precision, select

ModelName = Literal["text", "colpali"]


@dataclass
class Slot:
    model_id: str
    revision: str
    batch: int
    requested: str
    precision: str
    lock: Lock = field(default_factory=Lock)
    model: Any = None
    processor: Any = None
    status: str = "unloaded"
    device: str | None = None
    fallback: bool = False
    load_seconds: float | None = None
    error: str | None = None
    actual_precision: str | None = None

    def info(self) -> dict:
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "batch_size": self.batch,
            "state": self.status,
            "device": self.device,
            "fallback": self.fallback,
            "precision": self.actual_precision,
            "load_seconds": self.load_seconds,
            "error": self.error,
            "os": platform.system(),
            "arch": platform.machine(),
        }


class Registry:
    def __init__(self, cfg: Settings, metrics: Metrics):
        self.cfg, self.metrics = cfg, metrics
        self.slots = {
            "text": Slot(
                cfg.text_embedding_model_id,
                cfg.text_embedding_revision,
                cfg.text_embedding_batch_size,
                cfg.text_embedding_device,
                "fp32",
            ),
            "colpali": Slot(
                cfg.colpali_model_id,
                cfg.colpali_revision,
                cfg.colpali_batch_size,
                cfg.colpali_device,
                cfg.colpali_precision,
            ),
        }
        self.executor = ThreadPoolExecutor(
            max_workers=cfg.ai_max_concurrent_inferences, thread_name_prefix="inference"
        )
        self.capacity = BoundedSemaphore(cfg.ai_max_concurrent_inferences)

    def status(self) -> dict[str, dict]:
        return {name: slot.info() for name, slot in self.slots.items()}

    def _load(self, name: ModelName, slot: Slot, cpu: bool = False) -> None:

        if slot.model is not None:
            return
        slot.status = "loading"
        started = perf_counter()
        try:
            import torch

            device, fallback = select(
                "cpu" if cpu else slot.requested,
                self.cfg.ai_device,
                self.cfg.ai_allow_device_fallback,
                torch,
            )
            actual, dtype = precision(device, slot.precision, torch)
            kwargs = {"revision": slot.revision, "local_files_only": self.cfg.ai_offline}
            model_source = slot.model_id
            if self.cfg.ai_offline:
                from huggingface_hub import snapshot_download

                model_source = snapshot_download(
                    slot.model_id,
                    revision=slot.revision,
                    cache_dir=self.cfg.ai_model_cache_dir,
                    local_files_only=True,
                )
            if name == "text":
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    model_source,
                    cache_folder=str(self.cfg.ai_model_cache_dir),
                    device=device,
                    model_kwargs={"torch_dtype": dtype},
                    **kwargs,
                )
                processor = None
            else:
                from colpali_engine.models import ColPali, ColPaliProcessor

                kwargs.update(cache_dir=str(self.cfg.ai_model_cache_dir))
                processor = ColPaliProcessor.from_pretrained(model_source, **kwargs)
                model = ColPali.from_pretrained(
                    model_source,
                    torch_dtype=dtype,
                    device_map={"": device},
                    attn_implementation="eager",
                    **kwargs,
                )
            slot.model, slot.processor = model.eval(), processor
            slot.device, slot.actual_precision, slot.fallback = device, actual, cpu or fallback
            slot.error, slot.status = None, "ready"
        except Exception as exc:
            slot.status, slot.error = "failed", type(exc).__name__
            raise
        finally:
            slot.load_seconds = perf_counter() - started
            log.info("model_load", **slot.info())

    def _unload(self, slot: Slot) -> None:
        slot.status = "unloading"
        slot.model, slot.processor = None, None
        gc.collect()
        if slot.device == "cuda":
            import torch

            torch.cuda.empty_cache()
        elif slot.device == "mps":
            import torch

            torch.mps.empty_cache()
        slot.status = "unloaded"

    def unload(self, name: ModelName) -> None:
        slot = self.slots[name]
        with slot.lock:
            self._unload(slot)

    def _encode(self, name: ModelName, slot: Slot, inputs: list, mode: str) -> list[np.ndarray]:
        import torch

        output = []
        with torch.inference_mode():
            for i in range(0, len(inputs), slot.batch):
                batch = inputs[i : i + slot.batch]
                if name == "text":
                    fn = slot.model.encode_query if mode == "query" else slot.model.encode_document
                    result = validate_tensor(
                        fn(
                            batch,
                            batch_size=slot.batch,
                            normalize_embeddings=self.cfg.text_embedding_normalize,
                            convert_to_numpy=True,
                            show_progress_bar=False,
                        ),
                        2,
                    )
                    if result.shape != (len(batch), slot.model.get_sentence_embedding_dimension()):
                        raise ValueError("Unexpected dense batch shape")
                    output.extend(result)
                else:
                    features = (
                        slot.processor.process_queries(batch)
                        if mode == "query"
                        else slot.processor.process_images(batch)
                    )
                    if (
                        mode == "query"
                        and features["input_ids"].shape[1] > self.cfg.colpali_max_query_tokens
                    ):
                        raise ServiceError(
                            "query_too_long", "Visual query exceeds token budget.", "inference", 413
                        )
                    features = features.to(slot.device)
                    result = slot.model(**features)
                    if result.ndim != 3 or result.shape[0] != len(batch):
                        raise ValueError("Unexpected ColPali batch shape")
                    for tensor, mask in zip(result, features["attention_mask"]):
                        output.append(
                            validate_tensor(tensor[mask.bool()].detach().cpu().float().numpy(), 2)
                        )
                    del features, result
        return output

    def _work(self, name: ModelName, inputs: list, mode: str) -> tuple[list[np.ndarray], dict]:
        slot = self.slots[name]
        with slot.lock:
            try:
                self._load(name, slot)
                return self._result(name, slot, inputs, mode)
            except (RuntimeError, NotImplementedError, MemoryError) as exc:
                reason = str(exc).lower()
                oom = isinstance(exc, MemoryError) or "out of memory" in reason
                accelerator = slot.device in ("mps", "cuda") or any(d in reason for d in ("mps", "cuda"))
                if not (
                    accelerator
                    and self.cfg.ai_allow_device_fallback
                    and (
                        oom
                        or isinstance(exc, NotImplementedError)
                        or "not implemented" in reason
                        or "unsupported" in reason
                    )
                ):
                    raise
                log.warning(
                    "device_fallback", model=name, reason="memory" if oom else "unsupported_operation"
                )
            self._unload(slot)
            self._load(name, slot, cpu=True)
            return self._result(name, slot, inputs, mode)

    def _result(
        self, name: ModelName, slot: Slot, inputs: list, mode: str
    ) -> tuple[list[np.ndarray], dict]:
        with self.metrics.measure(name + "_inference"):
            start = perf_counter()
            values = self._encode(name, slot, inputs, mode) if inputs else []
            self.metrics.add(name + "_inputs_total", len(inputs))
            metadata = {
                **slot.info(),
                "inference_seconds": perf_counter() - start,
                "input_count": len(inputs),
                "dtype": "float32",
                "normalized": self.cfg.text_embedding_normalize if name == "text" else True,
            }
            if slot.processor:
                metadata["processor"] = type(slot.processor).__name__
                metadata["image_size"] = slot.processor.image_processor.size
            if values:
                metadata["dimensions"] = values[0].shape[-1]
            return values, metadata

    def run(
        self, name: ModelName, inputs: list[str] | list[Image.Image], mode: str
    ) -> tuple[list[np.ndarray], dict]:
        if not self.capacity.acquire(blocking=False):
            raise ServiceError("inference_busy", "Inference capacity is in use.", "inference", 429, True)
        # An expired caller must not invalidate images still in use by an inference thread.
        try:
            owned = [x.copy() if isinstance(x, Image.Image) else x for x in inputs]

            def execute():
                try:
                    return self._work(name, owned, mode)
                finally:
                    for item in owned:
                        if isinstance(item, Image.Image):
                            item.close()
                    self.capacity.release()

            future = self.executor.submit(copy_context().run, execute)
        except BaseException:
            self.capacity.release()
            raise

        try:
            return future.result(timeout=self.cfg.ai_inference_timeout_seconds)
        except FutureTimeout as exc:
            raise ServiceError(
                "inference_timeout", "Inference exceeded its time budget.", "inference", 504, True
            ) from exc
        except ServiceError:
            raise
        except Exception as exc:
            failed = self.slots[name].status != "ready"
            oom = isinstance(exc, MemoryError) or "out of memory" in str(exc).lower()
            code = (
                "out_of_memory" if oom else "model_load_failed" if failed else "model_inference_failed"
            )
            log.error("model_failure", model=name, code=code, exception=type(exc).__name__)
            raise ServiceError(
                code,
                "Model unavailable. Check dependencies, cache and device resources."
                if failed
                else "Model inference failed.",
                "model_load" if failed else "inference",
                503,
                oom,
            ) from exc

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
        for name, slot in self.slots.items():
            if slot.model is not None:
                self.unload(name)


def hardware() -> dict:
    try:
        import torch
    except ImportError:
        return {"cuda": False, "mps": False, "torch": False}
    cuda = torch.cuda.is_available()
    utilization = None
    if cuda:
        try:
            utilization = torch.cuda.utilization()
        except (ImportError, RuntimeError, OSError) as exc:
            log.debug("gpu_utilization_unavailable", exception=type(exc).__name__)
    return {
        "torch": True,
        "cuda": cuda,
        "mps": bool(torch.backends.mps.is_available()),
        "cuda_utilization_percent": utilization,
        "cuda_peak_memory_bytes": torch.cuda.max_memory_allocated() if cuda else None,
        "cuda_memory_allocated": torch.cuda.memory_allocated() if cuda else None,
    }
