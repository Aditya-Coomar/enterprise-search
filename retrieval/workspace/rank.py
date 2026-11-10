"""Rank one authorized document using AI artifacts. No model weights are loaded here."""

import hashlib
import json
import math
import re
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path

import numpy as np


def tokens(text):
    return re.findall(r"[^\W_]+", text.casefold())


def read_artifact(root, ref, prefix):
    if not ref["key"].startswith(prefix):
        raise ValueError("Unexpected artifact scope")
    path = (root / ref["key"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Invalid artifact location")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ValueError("Artifact integrity check failed")
    return data


def tensor(data, ref):
    arr = np.load(BytesIO(data), allow_pickle=False)
    if (
        arr.dtype.str != "<f4"
        or list(arr.shape) != ref["metadata"]["shape"]
        or arr.ndim != 2
    ):
        raise ValueError("Incompatible visual tensor")
    return arr


def compatible(a, b):
    return all(a.get(k) == b.get(k) for k in ("model_id", "revision", "dimensions"))


def rank(job):
    root = Path(job["root"]).resolve()
    prefix = job["prefix"]
    query = job["query"]
    query_terms = set(tokens(query))
    stopwords = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "in",
        "on",
        "at",
        "by",
        "of",
        "to",
        "for",
        "and",
        "or",
        "what",
        "which",
        "where",
        "who",
        "how",
        "does",
        "do",
        "did",
        "this",
        "that",
        "from",
        "as",
        "with",
        "can",
        "it",
        "its",
    }
    terms = query_terms - stopwords or query_terms
    mode = job["mode"]
    qdense = job.get("dense")
    qref = job.get("visual")
    qvis = tensor(read_artifact(root, qref, job["queryPrefix"]), qref) if qref else None
    pages = []
    for item in job["pages"]:
        arts = item["artifacts"]
        p = json.loads(read_artifact(root, arts["extraction"], prefix))
        blocks = (
            json.loads(read_artifact(root, arts["chunks"], prefix))["chunks"]
            if "chunks" in arts
            else []
        )
        pages.append((item, p, blocks, Counter(tokens(p["text"]))))
    df = {term: sum(counts[term] > 0 for _, _, _, counts in pages) for term in terms}
    average = sum(sum(c.values()) for *_, c in pages) / max(1, len(pages))
    results = []
    for item, p, blocks, counts in pages:
        n = p["page_number"]
        length = sum(counts.values())
        lex = sum(
            math.log1p((len(pages) - df[t] + 0.5) / (df[t] + 0.5))
            * counts[t]
            * 2.2
            / (counts[t] + 1.2 * (0.25 + 0.75 * length / max(1, average)))
            for t in terms
            if counts[t]
        )
        best_by_id = {}
        arts = item["artifacts"]
        if qdense and "text_embeddings" in arts:
            rows = json.loads(read_artifact(root, arts["text_embeddings"], prefix))
            q = np.asarray(qdense["vector"], dtype=np.float32)
            for row in rows:
                if compatible(qdense["metadata"], row["metadata"]):
                    vec = np.asarray(row["vector"], dtype=np.float32)
                    best_by_id[row["chunk_id"]] = float(
                        np.dot(vec, q)
                        / max(1e-9, np.linalg.norm(vec) * np.linalg.norm(q))
                    )
        dense = max(best_by_id.values(), default=None)
        vis = None
        if qvis is not None and item.get("visual"):
            ref = item["visual"]
            if compatible(qref["metadata"], ref["metadata"]):
                arr = tensor(read_artifact(root, ref, prefix), ref)
                vis = float((qvis @ arr.T).max(axis=1).mean())

        def passage_score(chunk, scores=best_by_id):
            return len(terms.intersection(tokens(chunk["text"]))) + scores.get(
                chunk["chunk_id"], 0
            )

        snippet = max(blocks, key=passage_score)["text"] if blocks else p["text"]
        words = re.split(r"(?<=[.!?])\s+|\n+", snippet.strip())
        sentence = max(
            words, key=lambda s: len(terms.intersection(tokens(s))), default=""
        )
        snippet = sentence[:420] if sentence else snippet[:420]
        results.append(
            {
                "page": n,
                "snippet": snippet,
                "lex": lex,
                "dense": dense,
                "visual": vis,
                "heading": next(
                    (e["text"][:100] for e in p["elements"] if e["kind"] == "heading"),
                    "",
                ),
            }
        )
    # Weighted reciprocal rank fusion. Equal scores receive equal ranks.
    features = (
        {"lex": 1.1, "dense": 1.0, "visual": 0.85}
        if mode == "hybrid"
        else ({"visual": 1} if mode == "visual" else {"lex": 1.1, "dense": 1})
    )
    for r in results:
        r["score"] = 0
    for feature, weight in features.items():
        ranked = sorted(
            (
                r
                for r in results
                if r[feature] is not None and (feature != "lex" or r[feature] > 0)
            ),
            key=lambda r: -r[feature],
        )
        last = None
        position = 0
        for i, r in enumerate(ranked, 1):
            if last != r[feature]:
                position = i
            last = r[feature]
            r["score"] += weight / (3 + position)
    if mode != "visual":
        best_dense = max(
            (r["dense"] for r in results if r["dense"] is not None), default=0
        )
        best_vis = max(
            (r["visual"] for r in results if r["visual"] is not None), default=0
        )
        results = [
            r
            for r in results
            if r["lex"] > 0
            or (r["dense"] is not None and r["dense"] >= max(0.24, best_dense - 0.14))
            or (r["visual"] is not None and r["visual"] >= max(0.2, best_vis - 0.025))
        ]
    results.sort(key=lambda r: (-r["score"], r["page"]))
    return [
        {
            "page": r["page"],
            "heading": r["heading"],
            "snippet": r["snippet"],
            "signals": [
                s
                for s, ok in [
                    ("Keyword", r["lex"] > 0 and mode != "visual"),
                    ("Semantic", r["dense"] is not None and mode != "visual"),
                    ("Visual", r["visual"] is not None and mode != "text"),
                ]
                if ok
            ],
        }
        for r in results
        if r["score"] > 0
    ][:30]


if __name__ == "__main__":
    print(json.dumps(rank(json.load(sys.stdin)), allow_nan=False))
