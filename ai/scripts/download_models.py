"""Download only the inference files for the configured, pinned model revisions."""

import argparse

from huggingface_hub import snapshot_download

from src.core.config import Settings


def download(name: str, settings: Settings) -> str:
    model, revision = (
        (settings.text_embedding_model_id, settings.text_embedding_revision)
        if name == "text"
        else (settings.colpali_model_id, settings.colpali_revision)
    )
    return snapshot_download(
        model,
        revision=revision,
        cache_dir=settings.ai_model_cache_dir,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"],
        ignore_patterns=["onnx/*", "openvino/*"],
        max_workers=2,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", choices=["text", "colpali"])
    args = parser.parse_args()
    settings = Settings()
    for name in args.models:
        print(download(name, settings))
