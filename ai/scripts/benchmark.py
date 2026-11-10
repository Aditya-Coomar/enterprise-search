"""Run one controlled cold pipeline followed by query evaluation over its artifacts."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from scripts.evaluate_extraction import evaluate
from src.core.config import Settings
from src.core.lifecycle import runtime
from src.core.runtime import configure_logging
from src.embeddings.tensors import deserialize
from src.models.registry import hardware
from src.schemas.contracts import Process


def rank(ordered: list[int], relevant: set[int], k: int) -> dict:
    hits = [i for i, p in enumerate(ordered, 1) if p in relevant]
    return {
        "recall_at_k": sum(i <= k for i in hits) / len(relevant),
        "reciprocal_rank": 1 / min(hits) if hits else 0,
    }


def benchmark(request: Process, labels: dict, cfg: Settings, k: int) -> dict:
    with runtime(cfg) as rt:
        start = perf_counter()
        manifest = rt.pipeline.run(request)
        elapsed = perf_counter() - start
        results = {
            "status": manifest.status,
            "processing_run_id": manifest.processing_run_id,
            "seconds": elapsed,
            "seconds_per_page": elapsed / len(manifest.pages),
            "models": rt.models.status(),
            "counters": rt.metrics.snapshot(),
            "hardware": hardware(),
            "ranking": [],
            "ocr": {},
        }
        for p in manifest.pages:
            ref = p.artifacts.get("extraction")
            if ref and (truth := labels.get("pages", {}).get(str(p.page_number))):
                results["ocr"][p.page_number] = evaluate(
                    truth, json.loads(rt.pipeline.read_artifact(ref))["text"]
                )
        for q in labels.get("queries", []):
            relevant = set(q["relevant_pages"])
            if not relevant:
                raise ValueError("Query needs relevant pages")
            for model, stage in (("text", "text_embeddings"), ("colpali", "visual_embeddings")):
                pages = [p for p in manifest.pages if stage in p.artifacts]
                if not pages:
                    continue
                queries, meta = rt.models.run(model, [q["query"]], "query")
                if model == "text":
                    repeated, _ = rt.models.run(model, [q["query"]], "query")
                    results.setdefault("dense_consistency", []).append(
                        {
                            "query_id": q["id"],
                            "dimensions": int(queries[0].size),
                            "max_absolute_difference": float(np.abs(queries[0] - repeated[0]).max()),
                        }
                    )
                scores = {}
                total_bytes = 0
                for p in pages:
                    ref = p.artifacts[stage]
                    data = rt.pipeline.read_artifact(ref)
                    total_bytes += len(data)
                    if model == "colpali":
                        doc = deserialize(data, ref.sha256, ref.metadata["shape"])
                        scores[p.page_number] = float((queries[0] @ doc.T).max(axis=1).sum())
                    else:
                        vectors = [row["vector"] for row in json.loads(data)]
                        if vectors:
                            scores[p.page_number] = float((queries[0] @ np.asarray(vectors).T).max())
                ordered = sorted(scores, key=scores.get, reverse=True)
                results["ranking"].append(
                    {
                        "query_id": q["id"],
                        "model": model,
                        "ranked_pages": ordered,
                        "artifact_bytes": total_bytes,
                        "query_seconds": meta["inference_seconds"],
                        **rank(ordered, relevant, k),
                    }
                )
        for model in ("text", "colpali"):
            duration = results["counters"].get(model + "_inference_seconds_total", 0)
            if duration:
                results.setdefault("inference_throughput", {})[model] = (
                    results["counters"].get(model + "_inputs_total", 0) / duration
                )
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    configure_logging("WARNING")
    print(
        json.dumps(
            benchmark(
                Process.model_validate_json(args.request.read_bytes()),
                json.loads(args.labels.read_bytes()) if args.labels else {},
                Settings(),
                args.k,
            ),
            indent=2,
        )
    )
