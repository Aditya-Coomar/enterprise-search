# Enterprise Search AI · Folio

Folio lets you upload a PDF, search it by words, meaning or visual content, and open the original page for each match. It works with native text, scanned pages, charts and tables. The browser talks to a local Node gateway; a Python service runs OCR and both embedding models. No hosted API key, Docker, database server or GPU is required for this workspace.

## Run on Windows

Use **64-bit Windows on an Intel or AMD PC** and PowerShell. The locked install uses CPU PyTorch. Allow several GB for the model downloads, plus space for dependencies and indexed PDFs. A short checkout path helps avoid Windows path-length errors.

**1. Install the prerequisites once.** These commands install Git, Node.js LTS (use 22.16 or newer), [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html):

```powershell
winget install -e --id Git.Git
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id astral-sh.uv
winget install -e --id UB-Mannheim.TesseractOCR
```

**2. Open a fresh PowerShell window.** Clone the repository that contains this README and enter its root. If you are running a pull request before it is merged, clone its source fork and check out its head branch.

```powershell
git clone https://github.com/Aditya-Coomar/enterprise-search.git
cd enterprise-search
```

**3. Set up the project once.** Run the commands below from the repository root. If Tesseract is installed elsewhere, adjust its path. Confirm that `eng` appears in the language list. The config helper creates a private key shared by the gateway and AI service; rerunning it preserves existing settings.

```powershell
$env:Path = "$env:ProgramFiles\Tesseract-OCR;$env:Path"
tesseract --list-langs
node scripts/init-config.mjs
uv python install 3.11
uv sync --directory ai --frozen --extra models --python 3.11
uv run --directory ai --frozen --extra models python -m scripts.download_models text colpali
npm.cmd ci --prefix api --ignore-scripts
npm.cmd ci --prefix web
npm.cmd run build --prefix web
```

The model download needs internet access on the first run. The checkpoints stay in `ai/model-cache`; after setup, upload and search run locally. If PyTorch reports a missing DLL on Windows, install the [Microsoft Visual C++ x64 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

**4. Start both services.** Each time you want to run the app, open two PowerShell terminals in the repository root and leave both running. In terminal 1 (AI and OCR):

```powershell
$env:Path = "$env:ProgramFiles\Tesseract-OCR;$env:Path"
uv run --directory ai --frozen --extra models python -m src.main
```

In terminal 2 (website and upload gateway):

```powershell
node api/src/workspace/server.mjs
```

**Open [the website on port 3108](http://127.0.0.1:3108).** Choose a PDF or open the sample report. Search for “Where are the replacement monitors stored?” to see the scanned log on page 4. Once visual indexing finishes, try “Solar share of electricity by month” in Visual mode to see the chart on page 3. CPU indexing can take a while. The [backend readiness check](http://127.0.0.1:8000/health/ready) and [API docs](http://127.0.0.1:8000/docs) are on port 8000. Press Ctrl+C in each terminal to stop.

**Optional verification:** with both services running, use a third PowerShell window at the repository root:

```powershell
.\ai\.venv\Scripts\python.exe web/scripts/verify_workspace.py
```

The check uploads the bundled report, verifies text, hybrid and visual results, checks page previews and session isolation, then deletes its test upload. To share the site temporarily, install [cloudflared](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/) and run `cloudflared tunnel --url http://127.0.0.1:3108` in another terminal. Share the generated HTTPS URL and keep all three processes running.

Uploads, session records, local keys, generated indexes, dependencies and model weights are excluded from Git. The sample report and lockfiles are included. See the [workspace guide](web/README.md) for data retention, the [AI service guide](ai/README.md) for the worker and Docker, and the [verification report](ai/docs/implementation-report.md) for tested environments and optional integrations.

## Platform architecture

AI and document intelligence service for the Enterprise Knowledge Search platform.

This service is responsible for document ingestion, parsing, OCR, content extraction, embedding generation and visual document understanding using ColPali.

It forms the AI processing layer of a larger enterprise knowledge platform built around hybrid retrieval, knowledge graphs and retrieval-augmented generation (RAG).

---

# 1. Overview

Traditional RAG systems primarily operate on extracted text and conventional vector embeddings.

Enterprise documents, however, contain significantly more information than plain text:

- Structured tables and financial reports.
- Charts and diagrams.
- Scanned documents.
- Complex layouts.
- Technical specifications.
- Cross-referenced documents.
- Visually structured information.

This service aims to preserve and process these different forms of information to support accurate enterprise search.

The AI service provides the document intelligence and model inference capabilities required by the platform.

## Core responsibilities

1. Document parsing and ingestion.
2. PDF processing and page rendering.
3. OCR and text extraction.
4. Document structure and layout extraction.
5. Text embedding generation.
6. Visual embedding generation using ColPali.
7. AI-assisted content and entity extraction.
8. Model lifecycle and inference management.
9. Processing job execution.

## Out of scope

The following responsibilities belong to other independent services:

| Responsibility | Owning service |
|---|---|
| User authentication and authorization | Enterprise Search API |
| Document and version management | Enterprise Search API / CockroachDB |
| Knowledge graph and entity relationships | Enterprise Search Knowledge |
| Graph traversal | Enterprise Search Knowledge |
| BM25 and lexical retrieval | Enterprise Search Retrieval |
| Hybrid retrieval orchestration | Enterprise Search Retrieval |
| ColPali candidate ranking orchestration | Enterprise Search Retrieval |
| Final answer generation | Retrieval / Answer Intelligence |

The AI service provides model inference capabilities rather than owning the complete enterprise search workflow.

---

# 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| API framework | FastAPI |
| ASGI server | Uvicorn |
| Validation | Pydantic |
| Configuration | Pydantic Settings |
| Deep learning | PyTorch |
| Model loading | Hugging Face Transformers |
| Visual retrieval model | ColPali |
| Text embeddings | Sentence Transformers |
| PDF processing | PyMuPDF |
| PDF utilities | pypdf |
| OCR | Tesseract |
| Image processing | Pillow |
| HTTP communication | HTTPX |
| Retry handling | Tenacity |
| Logging | Structlog |
| Package management | uv |
| Testing | Pytest |
| Linting | Ruff |

---

# 3. System Architecture

The AI service operates independently and communicates with the other platform services through internal APIs and processing workflows.

## High-level architecture

```text
                  ENTERPRISE SEARCH PLATFORM
                              |
                              |
                       EXPRESS API
                              |
                              |
                       AI SERVICE API
                              |
                 +------------+------------+
                 |            |            |
                 v            v            v
             INGESTION     EXTRACTION    INFERENCE
                 |            |            |
                 v            v            v
             PDF PARSER      OCR        MODEL ENGINE
                 |            |            |
                 v            v            |
             PAGE RENDERING   |            |
                 |            |            |
                 +------------+------------+
                              |
                              v
                       CONTENT PROCESSING
                              |
                +-------------+-------------+
                |                           |
                v                           v
          TEXT EMBEDDINGS             VISUAL EMBEDDINGS
                |                           |
                v                           v
          TEXT REPRESENTATION          COLPALI OUTPUT
                |                           |
                +-------------+-------------+
                              |
                              v
                       PROCESSING OUTPUT
                              |
                  +-----------+-----------+
                  |           |           |
                  v           v           v
              COCKROACHDB  OPENSEARCH  FALKORDB
              via owning   via owning   via owning
              services     services     service
```

The AI service should not directly own the persistence logic of CockroachDB, OpenSearch or FalkorDB.

It produces structured processing outputs, which are consumed by the respective owning services.

## Processing architecture

The processing pipeline is divided into independent stages.

```text
Document Received
       |
       v
File Validation
       |
       v
Document Classification
       |
       v
PDF Parsing
       |
       v
Page Rendering
       |
       +--------------------------+
       |                          |
       v                          v
   Text Extraction           Visual Processing
       |                          |
       v                          v
   OCR Processing              ColPali
       |                          |
       v                          v
   Text Normalization        Patch Embeddings
       |                          |
       v                          |
   Text Embeddings                |
       |                          |
       +-------------+------------+
                     |
                     v
             Structured Output
                     |
                     v
             Processing Complete
```

Individual stages should be independently testable and capable of being retried.

---

# 4. Proposed Folder Structure

```text
enterprise-search-ai/
│
├── src/
│   │
│   ├── api/
│   │   ├── routes/
│   │   ├── dependencies/
│   │   ├── middleware/
│   │   └── app.py
│   │
│   ├── ingestion/
│   │   ├── parsers/
│   │   ├── pdf/
│   │   ├── rendering/
│   │   └── validation/
│   │
│   ├── extraction/
│   │   ├── text/
│   │   ├── tables/
│   │   ├── layout/
│   │   ├── metadata/
│   │   └── ocr/
│   │
│   ├── embeddings/
│   │   ├── text/
│   │   ├── visual/
│   │   └── interfaces/
│   │
│   ├── models/
│   │   ├── colpali/
│   │   ├── text_embedding/
│   │   ├── llm/
│   │   └── registry/
│   │
│   ├── processing/
│   │   ├── pipelines/
│   │   ├── stages/
│   │   ├── orchestrator/
│   │   └── outputs/
│   │
│   ├── workers/
│   │   ├── processing_worker.py
│   │   └── task_executor.py
│   │
│   ├── clients/
│   │   ├── api_client.py
│   │   ├── storage_client.py
│   │   └── knowledge_client.py
│   │
│   ├── schemas/
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── lifecycle.py
│   │
│   └── main.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
│
├── models/
│   └── README.md
│
├── scripts/
│   ├── download_models.py
│   └── benchmark.py
│
├── .github/
│   └── workflows/
│
├── .env.example
├── .gitignore
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── requirements.txt
└── README.md
```

The structure separates model inference, document processing, API handling and background execution.

The `models/` directory should contain model management configuration rather than large model binaries committed to Git.

---

# 5. Core Modules

## 5.1 Ingestion

Responsible for receiving documents and preparing them for processing.

Supported initial formats:

- PDF
- Scanned PDF
- PNG
- JPEG

Future support:

- DOCX
- PPTX
- XLSX
- HTML
- TXT

Responsibilities:

- File validation.
- MIME type detection.
- Document classification.
- PDF parsing.
- Page extraction.
- Page rendering.
- Storage reference resolution.

## 5.2 Extraction

Extracts meaningful information from documents.

Capabilities:

- Native PDF text extraction.
- OCR.
- Table extraction.
- Heading detection.
- Section identification.
- Metadata extraction.
- Layout analysis.

Extracted information must retain its original document and page references.

## 5.3 Text Embeddings

Responsible for converting extracted text into semantic vector representations.

The embedding implementation should support interchangeable models.

Each generated embedding should retain:

- Model identifier.
- Model revision.
- Embedding dimensions.
- Source chunk identifier.
- Document version identifier.

Embedding generation should be batch-oriented wherever possible.

## 5.4 Visual Embeddings — ColPali

ColPali provides visual document representations.

Unlike conventional text embedding models, ColPali generates multiple patch embeddings for each document page.

This enables retrieval based on visual document content, including:

- Charts.
- Tables.
- Diagrams.
- Layout.
- Scanned content.
- Spatial relationships between elements.

The AI service owns ColPali model loading and inference.

It should expose a reusable inference interface that other services can consume.

Important: Do not reduce the complete ColPali representation to a single vector if the objective is to preserve late-interaction retrieval.

The Retrieval service is responsible for candidate selection, MaxSim ranking and retrieval orchestration.

## 5.5 Model Registry

A model registry abstraction should manage model configuration and lifecycle.

Each model configuration should include:

- Model identifier.
- Model provider.
- Model revision.
- Model type.
- Device configuration.
- Precision.
- Maximum batch size.
- Model loading status.

The implementation should support CPU and GPU execution.

Avoid loading the same large model multiple times unnecessarily.

---

# 6. API Design

The service will expose internal APIs using FastAPI.

Suggested endpoints:

## Health

```http
GET /health
GET /health/ready
```

## Document processing

```http
POST /api/v1/process
GET  /api/v1/process/{job_id}
```

## Text extraction

```http
POST /api/v1/extraction/text
POST /api/v1/extraction/ocr
```

## Embeddings

```http
POST /api/v1/embeddings/text
POST /api/v1/embeddings/visual
```

## Model management

```http
GET /api/v1/models
GET /api/v1/models/{model_id}/status
```

These are proposed internal interfaces. The final API contracts should be versioned and shared with the consuming services.

---

# 7. Processing Output

Every processing operation should produce a structured output.

Example:

```json
{
  "document_id": "doc-001",
  "document_version_id": "version-001",
  "status": "completed",
  "pages": [
    {
      "page_number": 1,
      "text": "Extracted document text",
      "chunks": [
        {
          "chunk_id": "chunk-001",
          "content": "Extracted content",
          "page_number": 1
        }
      ],
      "visual_embedding": {
        "model_id": "colpali",
        "model_revision": "configured-revision",
        "storage_reference": "embedding-reference"
      }
    }
  ]
}
```

The example is illustrative. Actual embedding values should be transferred using an efficient binary or object-storage representation rather than unnecessarily large JSON payloads.

Every output must retain document and version associations.

---

# 8. Configuration

Use environment variables through Pydantic Settings.

Example `.env.example`:

```env
APP_NAME=enterprise-search-ai
APP_ENV=development

HOST=0.0.0.0
PORT=8000

LOG_LEVEL=INFO

DEVICE=auto
MODEL_CACHE_DIR=./model-cache

COLPALI_MODEL_ID=
COLPALI_MODEL_REVISION=

TEXT_EMBEDDING_MODEL_ID=
TEXT_EMBEDDING_MODEL_REVISION=

BATCH_SIZE=4
MAX_CONCURRENT_INFERENCE=1

STORAGE_ENDPOINT=
STORAGE_BUCKET=
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=

API_INTERNAL_URL=
KNOWLEDGE_SERVICE_URL=
```

Never commit actual secrets or production environment files.

Model identifiers and hardware settings should be configurable without changing application code.

---

# 9. Development Setup

## Prerequisites

- Python 3.12 recommended for the initial dependency stack.
- uv.
- Git.
- NVIDIA GPU and compatible drivers for GPU inference.
- CUDA-compatible PyTorch installation when GPU acceleration is required.

## Clone repository

```bash
git clone <repository-url>
cd enterprise-search-ai
```

## Create virtual environment

```bash
uv python install 3.12

uv venv --python 3.12

.venv\Scripts\Activate.ps1
```

## Install dependencies

```bash
uv pip install -r requirements.txt
```

Alternatively, if managing the project through `pyproject.toml`:

```bash
uv sync
```

## Export requirements

```bash
uv export --format requirements-txt --output-file requirements.txt
```

Keep `pyproject.toml` and `uv.lock` as the primary dependency management files.

## Run development server

```bash
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation:

```text
http://localhost:8000/docs
```

---

# 10. GPU and Model Execution

ColPali and other deep learning models can consume significant GPU memory.

The service should support:

- CPU inference.
- CUDA inference.
- Configurable batch sizes.
- Configurable model precision.
- Lazy model loading where appropriate.
- Model reuse.
- Inference concurrency limits.

PyTorch should be installed with a build compatible with the target CUDA environment.

Do not assume that installing the latest CUDA toolkit automatically provides the correct PyTorch build.

For Windows development, verify GPU availability:

```python
import torch

print("CUDA available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM:", torch.cuda.get_device_properties(0).total_memory)
```

Production inference should ideally run in a Linux environment with a compatible NVIDIA runtime.

---

# 11. Testing and Code Quality

Testing should be organized into multiple levels.

## Unit tests

Test:

- PDF parsing.
- Text extraction.
- OCR processing.
- Chunk generation.
- Embedding generation.
- Model loading.
- Output serialization.

## Integration tests

Test:

- End-to-end document processing.
- Storage integration.
- Internal service communication.
- Model inference.
- Processing failure recovery.

## AI evaluation

Evaluate:

- OCR accuracy.
- Extraction accuracy.
- Embedding consistency.
- ColPali retrieval quality.
- Processing latency.
- GPU memory utilization.

## Commands

```bash
uv run pytest

uv run ruff check .

uv run ruff format .
```

---

# 12. Deployment

This repository is independently deployable.

It should contain its own Dockerfile and CI/CD workflow.

Suggested deployment configuration:

```text
enterprise-search-ai
        |
        v
    Docker Image
        |
        v
    AI Service
        |
        +---- FastAPI
        |
        +---- Processing Worker
        |
        +---- Model Runtime
```

The API and worker can initially share one codebase while running as separate processes when necessary.

For production, GPU-intensive inference should be isolated from lightweight document processing if their resource requirements differ.

The model cache should use persistent storage where appropriate to avoid repeatedly downloading model weights.

---

# 13. Integration with Other Services

| Service | Integration |
|---|---|
| Enterprise Search API | Receives processing requests and returns job status |
| Enterprise Search Knowledge | Supplies extracted content and entity-extraction capabilities |
| Enterprise Search Retrieval | Provides embedding and ColPali inference capabilities |
| CockroachDB | Persisted by the owning service |
| FalkorDB | Managed by Knowledge |
| OpenSearch | Managed by Retrieval |
| Object Storage | Stores source documents and generated assets |

The AI service should not directly depend on the internal database schemas of other services.

Communication should happen through versioned APIs and well-defined data contracts.

---

# 14. Engineering Principles

The following principles should be maintained throughout development:

1. **Model independence:** Model implementations should be interchangeable.
2. **Version awareness:** Every embedding must identify its generating model and revision.
3. **Page-level traceability:** Extracted information must retain its original page reference.
4. **Idempotent processing:** Retrying a failed processing stage must not corrupt existing outputs.
5. **Resource awareness:** GPU memory and inference concurrency must be controlled.
6. **Service independence:** The AI service should not depend on the internal implementation of the API, Knowledge or Retrieval services.
7. **Reproducibility:** Model configurations and processing parameters must be recorded.
8. **Separation of concerns:** Document processing, model inference and retrieval orchestration must remain separate responsibilities.

---

# 15. Long-Term Direction

The AI service will eventually evolve into a reusable document intelligence engine.

Beyond the initial PDF and ColPali implementation, it should be possible to introduce:

- DOCX and PPTX processing.
- Spreadsheet intelligence.
- Advanced table extraction.
- Multimodal embedding models.
- Improved OCR models.
- Document classification.
- Structured information extraction.
- Model evaluation and experimentation.
- Additional visual document models.

The architecture should allow these capabilities to be introduced independently without changing the external service contract.

**The primary objective is to build a reliable document intelligence layer that transforms unstructured enterprise documents into structured, searchable and traceable representations.**