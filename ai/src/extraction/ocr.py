import math
from collections import defaultdict
from time import monotonic

import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from src.core.config import Settings
from src.core.runtime import ServiceError, measure
from src.schemas.contracts import Element


def deskew_angle(gray: Image.Image) -> float:
    """Estimate mild document skew from horizontal ink-projection sharpness."""
    thumb = gray.copy()
    thumb.thumbnail((600, 600))

    def score(angle: int) -> float:
        rotated = thumb.rotate(angle, fillcolor=255)
        ink = np.asarray(rotated) < 150
        projection = ink.sum(axis=1).astype(float)
        return float(np.square(np.diff(projection)).sum())

    baseline = score(0)
    if baseline <= 0:
        return 0
    best = max(range(-4, 5), key=score)
    return best if score(best) > baseline * 1.25 else 0


def original_box(box, angle, width, height):
    if not angle:
        return box
    cx, cy = width / 2, height / 2
    theta = math.radians(angle)
    points = [
        (
            cx + (x - cx) * math.cos(theta) - (y - cy) * math.sin(theta),
            cy + (x - cx) * math.sin(theta) + (y - cy) * math.cos(theta),
        )
        for x in (box[0], box[2])
        for y in (box[1], box[3])
    ]
    return (
        max(0, min(x for x, _ in points)),
        max(0, min(y for _, y in points)),
        min(width, max(x for x, _ in points)),
        min(height, max(y for _, y in points)),
    )


def recognize(
    image: Image.Image, area: tuple[float, float, float, float], cfg: Settings
) -> tuple[list[Element], float | None]:
    gray = ImageOps.autocontrast(ImageOps.grayscale(image)).filter(ImageFilter.MedianFilter(3))
    angle = deskew_angle(gray) if cfg.ocr_deskew else 0
    if angle:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    start = monotonic()
    try:
        with measure("ocr"):
            data = pytesseract.image_to_data(
                gray,
                lang=cfg.ocr_languages,
                config=f"--psm {cfg.ocr_psm}",
                timeout=cfg.ocr_timeout_seconds,
                output_type=pytesseract.Output.DICT,
            )
    except (OSError, RuntimeError, pytesseract.TesseractError) as exc:
        timed_out = monotonic() - start >= cfg.ocr_timeout_seconds
        raise ServiceError(
            "ocr_timeout" if timed_out else "ocr_unavailable",
            "Tesseract timed out."
            if timed_out
            else "Tesseract failed. Check the executable and language packs.",
            "ocr",
            503,
            timed_out,
        ) from exc
    lines = defaultdict(list)
    confidences = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        x, y, w, h = (data[k][i] for k in ("left", "top", "width", "height"))
        lines[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(
            (word, x, y, x + w, y + h)
        )
        score = float(data["conf"][i])
        if score >= 0:
            confidences.append(score)
    x0, y0, x1, y1 = area
    sx, sy = (x1 - x0) / image.width, (y1 - y0) / image.height
    elements = []
    for words in lines.values():
        left, top, right, bottom = original_box(
            (
                min(w[1] for w in words),
                min(w[2] for w in words),
                max(w[3] for w in words),
                max(w[4] for w in words),
            ),
            angle,
            image.width,
            image.height,
        )
        bbox = (x0 + left * sx, y0 + top * sy, x0 + right * sx, y0 + bottom * sy)
        elements.append(Element(kind="paragraph", bbox=bbox, text=" ".join(w[0] for w in words)))
    return elements, sum(confidences) / len(confidences) if confidences else None
