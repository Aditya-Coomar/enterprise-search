import argparse
import json
from pathlib import Path


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def evaluate(expected: str, actual: str) -> dict:
    from collections import Counter

    if not expected.strip():
        raise ValueError("Reference must contain text")
    words = expected.split()
    observed = actual.split()
    return {
        "cer": distance(expected, actual) / len(expected),
        "wer": distance(words, observed) / len(words),
        "word_completeness": sum((Counter(words) & Counter(observed)).values()) / len(words),
        "reference_words": len(words),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Score extracted page text against UTF-8 ground truth")
    p.add_argument("expected", type=Path)
    p.add_argument("actual", type=Path)
    args = p.parse_args()
    print(
        json.dumps(
            evaluate(args.expected.read_text(encoding="utf-8"), args.actual.read_text(encoding="utf-8"))
        )
    )
