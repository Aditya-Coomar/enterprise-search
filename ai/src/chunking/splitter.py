import re
import unicodedata
from dataclasses import dataclass

from src.core.config import Settings, Strategy
from src.core.runtime import digest, json_bytes
from src.schemas.contracts import Chunk, Context, Page


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = text.replace("\u00ad\n", "").replace("\u00ad", "")
    text = "".join(c for c in text if c in "\t\n" or not unicodedata.category(c).startswith("C"))
    text = text.replace("\ufffd", " ")
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()).strip()


@dataclass
class Block:
    text: str
    kind: str
    table: str | None = None
    size: float = 0


def blocks(page: Page, repeated: set[str]) -> list[Block]:
    items: list[Block] = []
    previous_id = None
    for element in page.elements:
        if element.kind == "table":
            for table in page.tables:
                if table.bbox == element.bbox and table.text.strip():
                    items.append(Block(normalize(table.text), "table", table.table_id))
            previous_id = None
            continue
        if not element.text or (
            element.kind in ("header", "footer", "page_number")
            and (normalize(element.text) in repeated or element.kind == "page_number")
        ):
            continue
        x = (element.bbox[0] + element.bbox[2]) / 2
        y = (element.bbox[1] + element.bbox[3]) / 2
        if any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in page.tables):
            continue
        value = normalize(element.text)
        if value:
            if (
                element.paragraph_id is not None
                and element.paragraph_id == previous_id
                and element.kind == "paragraph"
                and items
                and items[-1].kind == "paragraph"
            ):
                items[-1].text = normalize(items[-1].text + "\n" + value)
            else:
                items.append(Block(value, element.kind, size=element.size or 0))
            previous_id = element.paragraph_id
    return items


def chunk_page(
    context: Context, page: Page, ref: str, cfg: Settings, strategy: Strategy, repeated: set[str]
) -> tuple[str, list[Chunk]]:
    parts = blocks(page, repeated)
    normalized = "\n\n".join(b.text for b in parts)
    ranges = []
    cursor = 0
    title = parent = None
    headings = []
    for b in parts:
        if b.kind == "heading":
            while headings and headings[-1][0] <= b.size:
                headings.pop()
            parent = headings[-1][1] if headings else None
            title = b.text
            headings.append((b.size, title))
        start, end = cursor, cursor + len(b.text)
        group = ranges[-1] if ranges else None
        boundary = (
            b.kind == "table"
            or group is None
            or group[4]
            or strategy == "paragraph"
            or (strategy == "heading" and (b.kind == "heading" or end - group[0] > cfg.chunk_size))
        )
        if boundary:
            ranges.append([start, end, title, parent, b.table])
        else:
            group[1] = end
        cursor = end + 2
    chunks = []
    for start, end, title, parent, table in ranges:
        while start < end:
            stop = end if table else min(start + cfg.chunk_size, end)
            if stop < end and strategy in ("heading", "paragraph", "page"):
                split = normalized.rfind(" ", start + cfg.chunk_size // 2, stop)
                if split > start:
                    stop = split
            text = normalized[start:stop]
            if text.strip():
                chunk_id = digest(
                    json_bytes([context.prefix, page.page_number, strategy, start, stop, table, text])
                )
                chunks.append(
                    Chunk(
                        **context.model_dump(
                            include={"tenant_id", "document_id", "document_version_id"}
                        ),
                        chunk_id=chunk_id,
                        page_number=page.page_number,
                        start=start,
                        end=stop,
                        section_title=title,
                        parent_section=parent,
                        strategy=strategy,
                        text=text,
                        token_count=len(re.findall(r"\w+|[^\w\s]", text)),
                        character_count=len(text),
                        source_ref=ref,
                        table_id=table,
                    )
                )
            if stop == end:
                break
            start = stop - cfg.chunk_overlap if strategy == "overlap" else stop
    return normalized, chunks
