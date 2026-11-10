import io
import itertools
import math
import re
import statistics
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

import pymupdf as fitz
from PIL import Image, ImageOps, UnidentifiedImageError

from src.core.config import Settings
from src.core.runtime import ServiceError, now
from src.extraction.layout import reading_order
from src.extraction.ocr import recognize
from src.extraction.tables import TableExtractor, ruled_tables
from src.schemas.contracts import Box, Element, Page, Source, Table
from src.storage.objects import safe_key

FORMATS = {
    "application/pdf": ((".pdf",), b"%PDF-"),
    "image/png": ((".png",), b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": ((".jpg", ".jpeg"), b"\xff\xd8\xff"),
}


def validate(data: bytes, source: Source, cfg: Settings) -> None:
    safe_key(source.key)
    if not data or len(data) > cfg.max_upload_bytes:
        raise ServiceError(
            "invalid_size",
            "Document is empty or exceeds the size limit.",
            "validation",
            413 if data else 422,
        )
    ext, signature = FORMATS[source.mime_type]
    if (
        source.mime_type not in cfg.supported_mime_types
        or PurePosixPath(source.key).suffix.lower() not in ext
        or not data.startswith(signature)
    ):
        raise ServiceError(
            "format_mismatch",
            "File extension, declared type and signature must agree.",
            "validation",
            415,
        )


def check_size(w: float, h: float) -> None:
    if not all(math.isfinite(v) and v > 0 for v in (w, h)):
        raise ServiceError("invalid_dimensions", "Page has invalid dimensions.", "render")


def encode(image: Image.Image, fmt: str) -> bytes:
    with io.BytesIO() as buf:
        image.save(buf, format=fmt)
        return buf.getvalue()


@dataclass(frozen=True)
class ExtractionAdapters:
    ocr: Callable[[Image.Image, Box, Settings], tuple[list[Element], float | None]]
    tables: TableExtractor = ruled_tables


class Document(Protocol):
    count: int
    metadata: dict

    def render(self, index: int) -> Image.Image: ...
    def extract(
        self, index: int, page_id: str, force: bool, render: Callable[[], Image.Image]
    ) -> Page: ...
    def images(self, index: int) -> list[int]: ...
    def extract_image(self, xref: int) -> tuple[str, bytes]: ...
    def close(self) -> None: ...


def build_page(
    index: int,
    page_id: str,
    w: float,
    h: float,
    kind: str,
    method: str,
    conf: float | None,
    elements: list[Element],
    tables: list[Table],
    coverage: float,
    warnings: list[str],
    cfg: Settings,
) -> Page:
    ordered = reading_order(elements, w)
    content = "\n\n".join(el.text for el in ordered if el.text)
    invalid = content.count("\ufffd") / max(1, len(content))
    if not content.strip():
        warnings.append("no_usable_text")
    if conf is not None and conf < cfg.ocr_min_confidence:
        warnings.append("low_ocr_confidence")
    return Page(
        page_id=page_id,
        page_number=index + 1,
        width=w,
        height=h,
        classification=kind,
        extraction_method=method,
        confidence=conf,
        text=content,
        elements=ordered,
        tables=tables,
        quality={
            "characters": len(content),
            "character_density": len(content) / (w * h),
            "invalid_ratio": invalid,
        },
        image_coverage=coverage,
        warnings=warnings,
        processed_at=now(),
    )


class ImageDocument:
    count = 1

    def __init__(self, data: bytes, cfg: Settings, adapters: ExtractionAdapters):
        self.adapters = adapters
        self.cfg = cfg
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > cfg.max_image_pixels:
                    raise ServiceError(
                        "pixel_limit", "Image exceeds the decoded pixel limit.", "validation", 413
                    )
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                oriented = ImageOps.exif_transpose(im)
                self.width, self.height = oriented.size
                self.metadata = {
                    "format": im.format,
                    "width": self.width,
                    "height": self.height,
                    "mode": im.mode,
                }
                oriented.thumbnail((cfg.max_image_side, cfg.max_image_side))
                if oriented.has_transparency_data:
                    rgba = oriented.convert("RGBA")
                    self.image = Image.new("RGB", rgba.size, "white")
                    self.image.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    self.image = oriented.convert("RGB")
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
            raise ServiceError("corrupted_image", "Image cannot be decoded.", "validation") from exc

    def render(self, index: int) -> Image.Image:
        return self.image.copy()

    def extract(self, index: int, page_id: str, force: bool, render: Callable[[], Image.Image]) -> Page:
        elements, conf = self.adapters.ocr(self.image, (0, 0, self.width, self.height), self.cfg)
        return build_page(
            index, page_id, self.width, self.height, "image", "ocr", conf, elements, [], 1, [], self.cfg
        )

    def images(self, index: int) -> list[int]:
        return []

    def extract_image(self, xref: int) -> tuple[str, bytes]:
        raise ServiceError("invalid_image_ref", "Raster sources have no embedded objects.", "extraction")

    def close(self) -> None:
        self.image.close()


def classify_element(text: str, size: float, font: str, median: float, y: float, h: float) -> str:
    if re.fullmatch(r"(?:Page\s+)?\d+(?:\s+of\s+\d+)?", text, re.IGNORECASE) and (
        y < h * 0.1 or y > h * 0.85
    ):
        return "page_number"
    if re.match(r"^(?:figure|table|fig\.)\s+\d", text, re.IGNORECASE):
        return "caption"
    if re.match(r"^(?:[•●▪]|\d+[.)]|[-*])\s", text):
        return "list"
    if size > median * 1.15 or ("bold" in font.lower() and len(text) < 120):
        return "heading"
    if y < h * 0.055:
        return "header"
    if y > h * 0.92:
        return "footer"
    return "paragraph"


class PDFDocument:
    def __init__(self, data: bytes, cfg: Settings, adapters: ExtractionAdapters):
        self.adapters = adapters
        self.cfg = cfg
        fitz.no_recommend_layout()
        try:
            self.pdf = fitz.open(stream=data, filetype="pdf")
        except (ValueError, RuntimeError) as exc:
            raise ServiceError("corrupted_pdf", "PDF cannot be opened.", "validation") from exc
        self.metadata = {k: v for k, v in (self.pdf.metadata or {}).items() if v}
        self.count = len(self.pdf)
        if self.pdf.needs_pass or not 0 < self.count <= cfg.max_pages or self.pdf.is_repaired:
            self.close()
            raise ServiceError(
                "invalid_pdf", "Encrypted, damaged, empty or over-limit PDF.", "validation"
            )

    def images(self, index: int) -> list[int]:
        return sorted({i[0] for i in self.pdf[index].get_images(full=True) if i[0] > 0})

    def extract_image(self, xref: int) -> tuple[str, bytes]:
        pdf = self.pdf
        for key in ("Width", "Height"):
            kind, value = pdf.xref_get_key(xref, key)
            if kind != "int" or int(value) <= 0:
                raise ServiceError("invalid_embedded_image", "Malformed embedded image.", "extraction")
        pixels = int(pdf.xref_get_key(xref, "Width")[1]) * int(pdf.xref_get_key(xref, "Height")[1])
        if pixels > self.cfg.max_image_pixels:
            raise ServiceError("pixel_limit", "Embedded image exceeds pixel limit.", "extraction", 413)
        item = pdf.extract_image(xref)
        return item["ext"], item["image"]

    def close(self) -> None:
        self.pdf.close()

    def render(self, index: int) -> Image.Image:
        p = self.pdf[index]
        w, h = p.rect.width, p.rect.height
        check_size(w, h)
        zoom = min(
            self.cfg.render_dpi / 72,
            self.cfg.max_image_side / max(w, h),
            math.sqrt(self.cfg.max_image_pixels / (w * h)),
        )
        pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csRGB)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def extract(self, index: int, page_id: str, force: bool, render: Callable[[], Image.Image]) -> Page:
        p = self.pdf[index]
        w, h = p.rect.width, p.rect.height
        check_size(w, h)

        def box(b):
            return tuple((fitz.Rect(b) * p.rotation_matrix) & p.rect)

        blocks = p.get_text("dict", sort=True, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)[
            "blocks"
        ]
        spans = [
            s for b in blocks for line in b.get("lines", []) for s in line["spans"] if s["text"].strip()
        ]
        median = statistics.median(s["size"] for s in spans) if spans else 0
        elements = []
        for b in blocks:
            lines = b.get("lines", [])
            for line in lines:
                parts = line["spans"]
                text = "".join(s["text"] for s in parts).strip()
                if text:
                    style = max(parts, key=lambda s: len(s["text"]))
                    bbox = box(line["bbox"])
                    elements.append(
                        Element(
                            kind=classify_element(
                                text, style["size"], style["font"], median, bbox[1], h
                            ),
                            bbox=bbox,
                            text=text,
                            paragraph_id=b["number"],
                            font=style["font"],
                            size=style["size"],
                        )
                    )
        native = " ".join(e.text for e in elements)
        images = [fitz.Rect(box(i["bbox"])) for i in p.get_image_info()]
        images = [r for r in images if not r.is_empty]
        coverage = min(1, sum(r.get_area() for r in images) / (w * h))
        density = len(native) / (w * h)
        low = (len(native) < self.cfg.native_min_chars and density < 0.003) or native.count(
            "\ufffd"
        ) > len(native) * 0.05
        areas = []
        for r in images:
            covered = sum((r & fitz.Rect(e.bbox)).get_area() for e in elements)
            if r.get_area() > 0.025 * w * h and covered < 0.015 * r.get_area():
                areas.append(r)
        kind = "scanned" if not native.strip() else "mixed" if areas else "native"
        warnings = []
        if any(
            a.bbox[2] < b.bbox[0] - 10 and abs(a.bbox[1] - b.bbox[1]) < 3
            for a, b in itertools.pairwise(elements)
        ):
            warnings.append("uncertain_column_order")
        method = "native"
        conf = None
        if low or force or areas:
            image = render()
            rects = [p.rect] if low or force else areas
            ocr_elements = []
            scores = []
            for r in rects:
                crop_box = (
                    math.floor(r.x0 * image.width / w),
                    math.floor(r.y0 * image.height / h),
                    math.ceil(r.x1 * image.width / w),
                    math.ceil(r.y1 * image.height / h),
                )
                with image.crop(crop_box) as crop:
                    found, score = self.adapters.ocr(crop, tuple(r), self.cfg)
                ocr_elements.extend(found)
                if score is not None:
                    scores.append(score)
            conf = sum(scores) / len(scores) if scores else None
            if low or force:
                if ocr_elements or not native or force:
                    elements = ocr_elements
                    method = "ocr"
                else:
                    warnings.append("ocr_empty_native_retained")
            else:
                elements.extend(ocr_elements)
                method = "native+ocr"
        elements.extend(Element(kind="image", bbox=tuple(r)) for r in images)
        tables = self.adapters.tables(p, page_id, box)
        elements.extend(Element(kind="table", bbox=t.bbox) for t in tables)
        return build_page(
            index, page_id, w, h, kind, method, conf, elements, tables, coverage, warnings, self.cfg
        )


PARSERS = {"application/pdf": PDFDocument, "image/png": ImageDocument, "image/jpeg": ImageDocument}


@contextmanager
def open_document(
    data: bytes, source: Source, cfg: Settings, adapters: ExtractionAdapters | None = None
) -> Iterator[Document]:
    validate(data, source, cfg)
    parsed = PARSERS[source.mime_type](data, cfg, adapters or ExtractionAdapters(ocr=recognize))
    try:
        yield parsed
    finally:
        parsed.close()
