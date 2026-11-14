import math
import re
from collections import Counter


def words(text):
    return re.findall(r"[^\W_]+", text.casefold())


def fallback_chunks(text):
    return [
        {"text": text[start : start + 1000]}
        for start in range(0, len(text), 850)
        if text[start : start + 1000].strip()
    ]


def retrieve_passages(pages, terms):
    candidates = []
    for page, blocks, similarities in pages:
        for index, block in enumerate(blocks):
            text = block["text"].strip()
            if not text:
                continue
            heading = block.get("section_title") or ""
            body_words = words(text)
            lexical_words = Counter(body_words)
            lexical_words.update(words(heading))
            candidates.append({
                "page": page,
                "index": index,
                "text": text,
                "heading": heading,
                "counts": lexical_words,
                "positions": [
                    (position, word) for position, word in enumerate(body_words) if word in terms
                ],
                "dense": similarities.get(block.get("chunk_id")),
            })
    if not candidates:
        return {"results": [], "evidence": []}

    count = len(candidates)
    average = max(1, sum(sum(item["counts"].values()) for item in candidates) / count)
    weights = {}
    for term in sorted(terms):
        frequency = sum(term in item["counts"] for item in candidates)
        weights[term] = math.log1p((count - frequency + 0.5) / (frequency + 0.5))

    for item in candidates:
        counts = item["counts"]
        length = sum(counts.values())
        item["lex"] = sum(
            weights[term] * counts[term] * 2.2
            / (counts[term] + 1.2 * (0.25 + 0.75 * length / average))
            for term in weights if counts[term]
        )
        item["fusion"] = 0.0

    for signal, cutoff in (("lex", 0), ("dense", 0.24)):
        ranked = sorted(
            (item for item in candidates if item[signal] is not None and item[signal] > cutoff),
            key=lambda item: -item[signal],
        )[:40]
        previous, position = None, 0
        for index, item in enumerate(ranked, 1):
            if item[signal] != previous:
                previous, position = item[signal], index
            item["fusion"] += 1 / (10 + position)

    shortlist = sorted(
        (item for item in candidates if item["fusion"]),
        key=lambda item: -item["fusion"],
    )[:40]
    weight_total = sum(weights.values()) or 1

    def relevance(item):
        coverage = sum(weight for term, weight in weights.items() if item["counts"][term]) / weight_total
        positions = item["positions"]
        distance = min(
            (right - left for (left, left_word), (right, right_word) in zip(positions, positions[1:])
             if left_word != right_word),
            default=None,
        )
        proximity = 0 if distance is None else 1 / (1 + distance / 12)
        return (
            2.5 * item["fusion"]
            + 0.36 * max(0, item["dense"] or 0)
            + 0.34 * coverage
            + 0.06 * proximity
        )

    shortlist.sort(key=relevance, reverse=True)
    return pack_context(shortlist, candidates)


def pack_context(shortlist, candidates):
    hits = {}
    for item in shortlist:
        page = item["page"]
        if page not in hits:
            hits[page] = {
                "page": page,
                "heading": item["heading"],
                "snippet": item["text"][:420],
                "signals": [
                    label for label, present in (
                        ("Keyword", item["lex"] > 0), ("Semantic", (item["dense"] or 0) > 0.24)
                    ) if present
                ],
            }

    by_position = {(item["page"], item["index"]): item for item in candidates}
    evidence = {}
    seen = set()
    remaining = 12000

    def add(item):
        nonlocal remaining
        page = item["page"]
        text, heading = item["text"], item["heading"]
        excerpt = (heading + "\n" + text) if heading and not text.startswith(heading) else text
        excerpt = excerpt[: min(remaining, 1800)]
        if excerpt in seen or remaining < 300 or len(evidence.get(page, [])) >= 4:
            return
        if page not in evidence and len(evidence) >= 6:
            return
        evidence.setdefault(page, []).append((item["index"], excerpt))
        seen.add(excerpt)
        remaining -= len(excerpt)

    for item in shortlist[:6]:
        add(item)
    for item in shortlist[:6]:
        for offset in (-1, 1):
            neighbor = by_position.get((item["page"], item["index"] + offset))
            if neighbor and neighbor["heading"] == item["heading"]:
                add(neighbor)
    for item in shortlist[6:]:
        add(item)
    return {
        "results": list(hits.values())[:30],
        "evidence": [
            {"page": page, "passages": [text for _, text in sorted(passages)]}
            for page, passages in evidence.items()
        ],
    }
