# Folio document search

Upload a PDF, search its pages and read the original page image beside each match. The website includes a four-page fictional field report with a budget table, energy chart and scanned inventory log. The page reader also exposes extracted text, OCR confidence when available, and detected tables.

## Run from the monorepo root

1. Set up the [AI service](../ai/README.md), its internal service key, Tesseract, and the pinned MiniLM and ColPali checkpoints. Use the local storage adapter for this single-host deployment.
2. Run the AI service from its own directory with `uv run --frozen --extra models python -m src.main`.
3. In another terminal run the following commands from the monorepo root:

```sh
npm ci --prefix web
npm ci --prefix api --ignore-scripts
npm run build --prefix web
node api/src/workspace/server.mjs
```

The interactive website opens at [localhost:3108](http://127.0.0.1:3108). The gateway serves the Next.js production export and same-origin browser API. To share the website run `cloudflared tunnel --url http://127.0.0.1:3108`. Keep the gateway, AI process and tunnel running.

## How it works

- The Express gateway creates a random HTTP-only session cookie and authorizes every document, page, search, retry and delete request against that session. Browsers never receive the AI key or choose storage keys. Uploads are size-limited and the AI parser validates the PDF. A workspace holds up to 12 documents.
- The shared object adapter stores originals and immutable AI artifacts under a generated tenant, document and version prefix. Gateway job records are atomically persisted in `api/.workspace-data`. Queued or interrupted jobs resume on restart. Records and documents are periodically cleaned up after 24 hours. Use **Library → Remove document** to delete one sooner.
- Text indexing runs first, with page rendering, OCR, layout, tables, chunking and MiniLM inference. ColPali then indexes pages in the background. Text search is available while the visual index is being built. Search results identify the contributing signals; temporary model unavailability is reported on screen.
- The `retrieval/workspace` module ranks a single document with BM25, cosine similarity over passage embeddings and full query-to-page ColPali MaxSim. Hybrid mode uses weighted reciprocal rank fusion. The ranking worker verifies checksums and model revisions. It reads the AI artifacts from disk and loads no model weights. A result links to a one-based page number and the stored preview.
- This deployment uses a local document collection and a browser session. Organization accounts, a fleet-wide OpenSearch index, and cross-document graph queries are separate platform capabilities. The existing AI API and its internal authentication remain independent.

## Configuration and checks

The gateway reads the service configuration from `ai/.env`. Optional overrides are `AI_BASE_URL`, `WORKSPACE_PORT`, `WORKSPACE_STATE` and `RETRIEVAL_PYTHON`. The default retrieval interpreter is the AI virtual environment, which supplies NumPy. Use an absolute `STORAGE_ROOT` or a path relative to `ai/` for both processes. Run a single gateway instance against each state directory.

Run `ai/.venv/bin/python web/scripts/verify_workspace.py` from the monorepo root for the real two-session acceptance test, or pass `--base-url` to test a deployed workspace. The script uploads only the bundled synthetic report and deletes its test document.
