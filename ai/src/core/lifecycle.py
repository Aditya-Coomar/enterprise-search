from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

import httpx

from src.core.config import Settings
from src.core.runtime import Metrics
from src.extraction.candidates import OpenAICompatible
from src.models.registry import Registry
from src.processing.pipeline import Pipeline
from src.storage.objects import LocalStore, S3Store


@contextmanager
def runtime(cfg: Settings):
    with ExitStack() as stack:
        metrics = Metrics()
        store = LocalStore(cfg) if cfg.storage_backend == "local" else S3Store(cfg)
        stack.callback(store.close)
        http = stack.enter_context(httpx.Client(timeout=cfg.llm_timeout, follow_redirects=False))
        models = Registry(cfg, metrics)
        stack.callback(models.close)
        provider = OpenAICompatible(cfg, http)
        for model in models.slots if not cfg.ai_lazy_model_loading else cfg.ai_required_models:
            models.run(model, [], "load")
        yield SimpleNamespace(
            cfg=cfg,
            metrics=metrics,
            store=store,
            models=models,
            provider=provider,
            pipeline=Pipeline(cfg, store, models, provider, metrics),
        )
