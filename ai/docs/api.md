# HTTP API

The default internal prefix is `/api/v1`. Every route under it requires `X-Internal-Key`. The three public probes return only health state. Clients can inspect the generated schemas at `/openapi.json` and submit examples at `/docs`.

| Method and path | Body | Result |
| --- | --- | --- |
| GET /health, /health/live | — | Liveness |
| GET /health/ready | — | Storage reachability and required loaded models |
| POST /api/v1/process | Process | Completed, partial or failed manifest |
| POST /api/v1/extraction/text | Process | Manifest and page text with confidence and quality |
| POST /api/v1/extraction/ocr | Process | Forced OCR and page text |
| POST /api/v1/extraction/tables | Process | Tables with boxes, rows and text |
| POST /api/v1/extraction/layout | Process | Ordered elements, dimensions and coordinates |
| POST /api/v1/embeddings/text | Passage | Dense vector, chunk ID, version and model metadata |
| POST /api/v1/embeddings/text/batch | Batch | Ordered list of dense results |
| POST /api/v1/embeddings/query | Query | Dense query vector and model metadata |
| POST /api/v1/embeddings/visual/pages | Process | Per-page tensor references and exact shapes in the manifest |
| POST /api/v1/embeddings/visual/query | Query | Checksummed query tensor reference |
| POST /api/v1/entities/extract | Passage | Entity candidates, evidence, provenance and token usage |
| POST /api/v1/relationships/extract | Passage | Relationship candidates, evidence, provenance and token usage |
| GET /api/v1/models | — | Safe runtime and hardware metadata |
| GET /api/v1/models/{model_id}, /api/v1/models/{model_id}/status | — | Model status by alias `text` or `colpali` |
| GET /api/v1/metrics | — | Process-local counters, durations and available memory |

### Process

```json
{
  "tenant_id": "acme", "document_id": "report", "document_version_id": "v1",
  "source": {"key": "tenant/acme/documents/report/versions/v1/original/report.pdf", "mime_type": "application/pdf"},
  "pages": [1], "stages": ["render", "chunks"], "strategy": "heading", "idempotency_key": "job-17"
}
```

The source optionally includes a lowercase SHA-256. Omit pages for the full document. Page numbers are one-based. Available stages are `render`, `extraction`, `chunks`, `text_embeddings`, `visual_embeddings`, `entities` and `relationships`. Dependencies are resolved automatically. Dedicated extraction and visual endpoints select their corresponding stages.

### Passage, batch and query

```json
{"tenant_id":"acme","document_id":"report","document_version_id":"v1","page_number":1,"chunk_id":"c1","text":"Ada approved Project Mercury."}
```

Batch requests wrap passages in `{"items":[...]}`. All items belong to the same version. Query requests contain `{"tenant_id":"acme","text":"Who approved Mercury?"}`. Query artifacts are scoped to the tenant.

### Results and errors

A completed HTTP call can return a manifest whose `status` is `partial` or `failed`. Always inspect `failed_pages` and each page's `stages`, `artifacts`, `warnings` and `errors`. Processing responses include the source digest, run ID, timestamps, model revisions, configuration and persisted manifest key. See the [integration guide](integration.md) for the consumer contract.

```json
{"error":{"code":"inference_busy","message":"Inference capacity is in use.","stage":"inference","retryable":true}}
```

Errors include a request ID where available. Authentication failures use 401, missing inputs 404, size violations 413, unsupported MIME types 415 and invalid input 422. Capacity exhaustion uses 429. Provider and storage failures use 5xx, and inference deadline expiry uses 504. Express owns job status. The worker exits 0 on success, 2 for a manifest with failures and 1 for a rejected job.
