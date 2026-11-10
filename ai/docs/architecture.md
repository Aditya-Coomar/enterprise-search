# Architecture

The Express API submits an immutable source reference and a set of requested stages. FastAPI dispatches synchronous processing on its thread pool. The worker CLI invokes the same pipeline directly. Each process admits one document at a time because PyMuPDF requires serialized access. Independent inference calls use a bounded executor and reuse a registry per process. Use a single API worker per model-serving instance when memory is constrained.

| Module | Responsibility |
| --- | --- |
| src/api, src/core, src/schemas | HTTP contracts, bounded JSON bodies, internal key checks, startup/shutdown, settings, error handling and structured metrics |
| src/ingestion, src/extraction | Signature checks, document parsers, page rendering, Tesseract OCR, layout, native table extraction and LLM candidates |
| src/chunking | Normalized page content, deterministic chunking and provenance |
| src/models, src/embeddings | Device discovery, model lifecycle, bounded dense and full multi-vector inference, portable serialization |
| src/storage | Scoped object keys, local atomic files, boto3, checksummed artifacts and presigned S3 URLs |
| src/processing, src/workers | Stage dependencies, page checkpoints, manifests and one-request worker execution |
| scripts, tests | Fixture generation, environment checks, evaluation, model prefetch and CPU tests |

The platform repository originally contained a UTF-16 Windows dependency snapshot. The project declares direct dependencies in pyproject.toml and locks compatible transitive packages in uv.lock for macOS ARM64, Windows AMD64 and Linux x86-64/ARM64. Sentence Transformers, PyTorch and colpali-engine are an installable model extra. PyMuPDF provides native table detection as well as parsing and rendering. Pillow processes raster inputs. pytesseract invokes the external OCR executable. boto3 provides the S3 protocol. httpx supplies a reusable HTTP client for inference providers. psutil exposes available memory. pytest, moto and Ruff are development dependencies.

Model outputs are returned to Retrieval via explicit references. Express owns durable job state, retries and authorization. Knowledge owns entity resolution and graph writes. Run-level keys, page receipts and manifests are stored with document artifacts. No separate job broker or application database is required.
