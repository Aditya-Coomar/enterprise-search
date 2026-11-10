# Enterprise Search AI

The AI service turns versioned PDF, PNG and JPEG objects into page images, text, layout, tables, chunks, dense vectors, ColPali multi-vector tensors and evidence-grounded knowledge candidates. Its HTTP API and one-job worker share the same processing pipeline.

## Run locally

Use Python 3.11 or 3.12, uv, and Tesseract with the language data selected by `OCR_LANGUAGES`. On macOS install Tesseract via Homebrew. On Debian or Ubuntu install `tesseract-ocr` and `tesseract-ocr-eng`. On Windows install a Tesseract distribution and add its executable directory to PATH. Check with `tesseract --list-langs`.

From the repository's `ai` directory:

```sh
uv sync --frozen --extra models --python 3.11
uv run --frozen --extra models python -m scripts.verify_environment
```

Copy `.env.example` to `.env` and set `INTERNAL_API_KEY` to a private random value of at least 16 characters. Set `AI_DEVICE=cpu` to reproduce CPU results. The defaults use local object storage and lazy, offline model loading. Prefetch the weights once for embedding requests.

```sh
uv run --frozen --extra models python -m scripts.download_models text colpali
uv run --frozen --extra models python -m src.main
```

Open [the local API explorer](http://127.0.0.1:8000/docs) and enter the service key under **Authorize**. The default bind address is loopback. The `/health/ready` probe checks configured dependencies. Required models can be specified in `AI_REQUIRED_MODELS`. For text extraction and OCR alone, use `uv sync --frozen` and request the extraction stages.

## Process a document

Generate a native/scanned two-page fixture, a request and relevance labels in the ignored local object directory. The default request runs rendering, extraction, chunking and both embedding models.

```sh
uv run --frozen --extra models python -m scripts.sample_document objects/demo-job
uv run --frozen --extra models python -m src.workers.processing_worker objects/demo-job/request.json
```

The worker writes one JSON manifest to stdout and diagnostic logs to stderr. Submit the same JSON to `POST /api/v1/process` to run through HTTP. Inspect each page's status, errors and artifact keys. Original bytes stay under the source key. Set up an OpenAI-compatible endpoint and request `entities` or `relationships` to add candidate extraction.

## Verify

```sh
uv run --frozen --extra models pytest -q
uv run --frozen ruff check src scripts tests
uv run --frozen --extra models python -m scripts.benchmark objects/demo-job/request.json --labels objects/demo-job/labels.json --k 1
```

Set `RUN_MODEL_TESTS=1` for real pretrained CPU integration tests. Set `TEST_LOCAL_S3_ENDPOINT` to a loopback S3 emulator for a real HTTP storage check. Set these variables in your shell or PowerShell environment before invoking pytest. A previous completed request exercises the cache. Use a fresh local storage root or a new idempotency key to measure cold processing.

## Docker

```sh
docker build -t enterprise-search-ai:local .
docker run --rm --env-file .env -e HOST=0.0.0.0 -e AI_MODEL_CACHE_DIR=/data/models -e STORAGE_ROOT=/data/objects -p 127.0.0.1:8000:8000 -v enterprise-ai-data:/data enterprise-search-ai:local
```

Populate the same volume by running the image with `python -m scripts.download_models text colpali` as its command. An existing Hugging Face cache can also be mounted at `/data/models`. When using a host .env that sets relative storage paths, pass the explicit container path overrides to both commands. For a worker, mount the request JSON and use `python -m src.workers.processing_worker /input/request.json`. The image runs as UID 10001 and includes English OCR data.

## Service documentation

- [Architecture and dependencies](docs/architecture.md)
- [API contracts, authentication and examples](docs/api.md)
- [Processing stages, artifacts and retries](docs/processing-pipeline.md)
- [Model management, hardware and serialization](docs/model-management.md)
- [Integration and ownership](docs/integration.md)
- [Implementation and verification report](docs/implementation-report.md)
