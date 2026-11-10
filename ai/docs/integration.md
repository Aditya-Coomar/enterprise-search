# Platform integration

**Express API.** Write the original object below the authorized tenant, document and version prefix. Send that scoped key and optional SHA-256 to the AI service over the internal network. A process call returns after completion. The API owns durable jobs, version management, authorization and retry policy. An interrupted client should resubmit the same request and idempotency key.

**Object storage.** Set STORAGE_BACKEND=s3, STORAGE_BUCKET and STORAGE_REGION. For an S3-compatible deployment also set STORAGE_ENDPOINT. Use an IAM role or configure the access/secret pair through environment secrets. Grant read access to approved source objects plus read/write access to derived keys. The SDK adapter supports head, bounded reads, write, derived-only delete and short-lived signed reads. The local adapter maps logical keys into STORAGE_ROOT. For local imports use LocalStore.path(key), as uppercase characters have a reserved encoding to preserve tenant and object identity on case-insensitive volumes. The adapter rejects symlinks and publishes via same-directory atomic replacement. Local storage is a real development backend. Signed URLs require S3. No HTTP input URL is accepted as a document source.

**Retrieval.** Read the manifest's per-page chunk artifact and corresponding text-vector records. Join by chunk ID and document version ID. For a visual artifact, read its key, verify SHA-256 and decode the NPY bytes using the declared format version. Reject incompatible model ID/revision or dimension pairs. Call the query endpoints on this service to keep encoding consistent. Retrieval owns indexing, candidate retrieval, MaxSim and fusion.

**Knowledge.** Configure LLM_PROVIDER=openai-compatible, LLM_ENDPOINT as a trusted base URL including its version prefix, LLM_MODEL and any required LLM_API_KEY. Request only the stages the deployment is configured to run. The adapter posts to the provider's chat completions endpoint using JSON Schema. Set LLM_RESPONSE_FORMAT=json_object for a provider that only supports JSON object mode. Both modes validate evidence and the response schema locally. The service validates literal evidence and typed mentions or relationship endpoints, adds document/version/page/chunk identity and reports provider or validation failures. Knowledge owns identity resolution and persistence.

An example page fragment, with identifiers abbreviated for readability:

```json
{
  "page_number": 1,
  "classification": "native",
  "stages": {"extraction":"success","ocr":"skipped","chunks":"success"},
  "artifacts": {"chunks":{"key":"tenant/acme/documents/report/versions/v1/derived/1.0.0/<run>/pages/1/chunks-<sha>.json","sha256":"<sha>","size":860,"media_type":"application/json","created_at":"2026-11-10T12:00:00Z","metadata":{"document_version_id":"v1"}}},
  "warnings": [], "errors": []
}
```

Source contains tenant data. Scope storage access to trusted service identities, run the API behind internal TLS and configure trusted provider endpoints appropriate for that data. Structured logs omit document text, prompts and vectors. Public probes return only status. Internal model and metrics routes expose diagnostics.
