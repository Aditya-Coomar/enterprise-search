FROM ghcr.io/astral-sh/uv:0.8.17 AS uv
FROM python:3.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 STORAGE_ROOT=/data/objects AI_MODEL_CACHE_DIR=/data/models
RUN apt-get update && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-eng libgomp1 \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 ai
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra models --no-install-project --no-cache
ARG TORCH_ACCELERATOR=cpu
RUN case "$TORCH_ACCELERATOR" in \
    cpu) true ;; \
    cu128) uv pip install --python /app/.venv/bin/python --no-cache --reinstall-package torch --reinstall-package torchvision \
        --index https://download.pytorch.org/whl/cu128 "torch==2.8.0+cu128" "torchvision==0.23.0+cu128" ;; \
    *) exit 2 ;; esac
COPY src ./src
COPY scripts ./scripts
RUN mkdir -p /data/models /data/objects && chown -R ai:ai /data
USER ai
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health/live',timeout=3)"
CMD ["python","-m","src.main"]
