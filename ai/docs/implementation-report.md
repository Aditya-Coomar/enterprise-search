# Implementation and verification

The service was built in the monorepo's ai directory from its original dependency export. The API, worker and evaluation commands use the same production parsers, storage adapters, models and candidate provider.

## Deliverables

| Area | Implementation | Evidence |
| --- | --- | --- |
| Application | FastAPI factory, settings, lifecycle, internal key authentication, request size bounds, structured errors, readiness and metrics | tests/test_foundation.py, tests/test_pipeline.py |
| Documents | PDF, PNG and JPEG signature checks, resource limits, native text and image extraction, mixed pages, OCR, layout and native ruled tables | tests/test_ingestion.py, tests/test_quality.py, tests/fixtures/documents.py |
| Chunking | Five configurable strategies, normalized offsets, section metadata, page provenance and indivisible tables | tests/test_chunks.py |
| Models | Lazy, revision-pinned Sentence Transformers and ColPali adapters, central device selection, timeout handling, lifecycle and safe binary interchange | tests/test_models.py, tests/test_model_limits.py |
| Knowledge | Versioned structured prompt, type and evidence validation, source provenance, bounded retries and token usage | tests/test_candidates.py, tests/test_live_llm.py |
| Storage and orchestration | Local and S3 adapters, per-page stage receipts, immutable content-addressed artifacts, partial manifests and idempotent retries | tests/test_pipeline.py, tests/test_live_storage.py, tests/test_full_stack.py |
| API and deployment | Authenticated processing, extraction, embedding, knowledge, model and metrics endpoints, standalone worker, lockfile, Linux CPU Docker image and optional CUDA build | docs/api.md, Dockerfile, src/workers/processing_worker.py, ../.github/workflows/ai.yml |
| Evaluation | Controlled document fixtures, CER, WER, completeness, dense consistency, latency, throughput, storage size, Recall@K and reciprocal rank | scripts/sample_document.py, scripts/evaluate_extraction.py, scripts/benchmark.py |

The [architecture guide](architecture.md) maps source modules and dependencies. The [API guide](api.md) lists every route and request family. The [service README](../README.md) contains startup, worker and Docker commands. Regenerate the pip export with `python -m scripts.export_requirements` after updating the uv lock.

## Verification results

| Check | Result on this checkout |
| --- | --- |
| Ordinary CPU suite | 37 passed, five opt-in tests skipped |
| Complete suite with live S3, local LLM, pinned pretrained weights and full-stack tests enabled | 42 passed, zero skips, in 90.80 seconds |
| Ruff lint and format verification | Passed |
| Dependency and configuration checks | uv lock matched pyproject.toml, the pip export was regenerated and all 60 settings appeared in .env.example |
| HTTP contract | OpenAPI exposed 19 paths, with internal key authentication on all 16 internal paths |
| Container | Final Linux ARM64 image built and passed HTTP, OCR and worker smoke checks |

The suite emitted dependency deprecation warnings from PyMuPDF bindings, the FastAPI test client and the Sentence Transformers dimension accessor. No test failed in the final run.

## Real execution evidence

- **macOS ARM64, Python 3.11.13, FP32 CPU.** The pinned MiniLM model produced 384-dimensional passage and query vectors. ColPali's official processor and learned checkpoint encoded pages and queries. A single test image produced 1,031 sequence positions of dimension 128. The query “Revenue” produced 12 positions of dimension 128. The tensor survived a binary round trip and reference MaxSim scoring. The opt-in suite also exercises a real two-image inference batch.
- **Apple Metal.** A separate physical MPS run encoded a document and query with each model, with device fallback disabled. MiniLM ran in FP32 and ColPali in FP16. ColPali returned finite page and query tensors of shapes [1031, 128] and [12, 128].
- **S3-compatible HTTP.** LocalStack accepted source uploads, head checks, derived writes, manifest reads and artifact downloads. Independent SDK reads verified returned checksums. Tests used unique temporary buckets and removed them on completion.
- **LLM integration.** An isolated local Ollama server loaded qwen2.5:3b. Entity and relationship calls used the OpenAI-compatible JSON Schema adapter. An early prompt missed an approval when a second sentence discussed inventory. The versioned prompt includes a worked example. The full-stack test checks for the actual APPROVED_BY relationship between Project Mercury and Ada Patel, grounded in a mixed native/OCR page. A schema-valid empty answer fails that test.
- **Linux ARM64.** Built the CPU Docker image with frozen dependencies and verified the running HTTP service as UID 10001. A native/scanned two-page PDF produced the expected OCR text. The separate worker returned the same persisted manifest.
- **Recovery.** A controlled OCR failure affected one page, preserved the successful page artifacts and returned a partial manifest. An identical retry reused the successful checkpoints and recovered the failed page. Another test deletes a derived artifact and checks that retry restores it.

## Measured two-page benchmark

The labeled fixture contains one native finance page and one scanned inventory page. With both encoders on CPU, a cold logical run with cached weights processed the two pages in **55.62 seconds**, including **24.10 seconds** to load ColPali. The two visual artifacts totaled **1,056,000 bytes**. Each of the two queries ranked its relevant page first using both dense similarity and reference MaxSim. The scanned page had zero character and word errors. Repeated dense query encodings had a maximum absolute difference of zero. This small fixture measures functional compatibility. Representative production documents are needed for capacity planning and retrieval-quality estimates.

The machine-readable receipt for this checkout is `objects/demo-job/benchmark.json`. Generate a fresh measurement with the benchmark command in the README. Model caches, local service credentials, generated PDFs, processing artifacts and benchmark output are excluded from Git.

## Reproducing external checks

The ordinary tests run on CPU without downloading model weights. The optional acceptance suite requires the pinned weights, a loopback S3-compatible endpoint, and a configured OpenAI-compatible provider. Set the following environment values and run `uv run --frozen --extra models pytest -q`:

```dotenv
RUN_MODEL_TESTS=1
RUN_LLM_TESTS=1
RUN_FULL_STACK_TEST=1
TEST_LOCAL_S3_ENDPOINT=http://127.0.0.1:4566
LLM_PROVIDER=openai-compatible
LLM_ENDPOINT=http://127.0.0.1:19474/v1
LLM_MODEL=qwen2.5:3b
LLM_TIMEOUT=120
HF_HUB_OFFLINE=1
OMP_NUM_THREADS=4
```

For this checkout, the optional Ollama weights are in `model-cache/ollama-test`. To reuse them, set `OLLAMA_MODELS` to the absolute path of that directory, set `OLLAMA_HOST=127.0.0.1:19474` and start `ollama serve` in a separate terminal. The S3 test uses the synthetic credentials expected by LocalStack. Production deployments need their own provider configuration and S3 permissions.

## Outstanding platform verification and limits

Native Windows execution, NVIDIA CUDA acceleration, the CUDA image and the other repositories' deployed callers have not been exercised here. The workflow includes Windows, macOS and Linux CPU jobs. Production object storage, IAM and private LLM endpoints require deployment-specific checks.

The parser supports PDF, PNG and JPEG. Layout and column detection are heuristic. Ruled native tables retain cell structure. Scanned tables produce OCR text and page images. OCR quality and LLM recall depend on document and model quality. A timeout releases the caller while an in-flight native inference can continue holding its slot. The service serializes document processing per process. Express owns durable scheduling and job status.
