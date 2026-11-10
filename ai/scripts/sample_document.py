"""Create a small labeled two-page PDF and a job for the local adapter."""

import argparse
import json
from pathlib import Path

import pymupdf

from src.core.config import Settings
from src.core.runtime import digest
from src.schemas.contracts import Process
from src.storage.objects import LocalStore

PAGES = [
    "The finance team approved a copper procurement budget of 5000 dollars.",
    "The warehouse inventory includes fifty replacement computer monitors.",
]


def create(root: Path, cfg: Settings) -> Path:
    if cfg.storage_backend != "local":
        raise ValueError("The fixture generator requires local storage")
    doc = pymupdf.open()
    for i, text in enumerate(PAGES):
        page = doc.new_page(width=540, height=320)
        if i == 0:
            page.insert_text((24, 100), text, fontsize=12)
        else:
            with pymupdf.open() as temporary:
                image = temporary.new_page(width=540, height=320)
                image.insert_text((24, 100), text, fontsize=12)
                page.insert_image(
                    page.rect, stream=image.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
                )
    data = doc.tobytes(no_new_id=True)
    doc.close()
    key = "tenant/demo/documents/fixture/versions/" + digest(data)[:16] + "/original/example.pdf"
    store = LocalStore(cfg)
    path = store.path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    request = Process(
        tenant_id="demo",
        document_id="fixture",
        document_version_id=digest(data)[:16],
        source={"key": key, "mime_type": "application/pdf", "sha256": digest(data)},
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "request.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")
    (root / "labels.json").write_text(
        json.dumps(
            {
                "pages": dict(enumerate(PAGES, 1)),
                "queries": [
                    {
                        "id": "budget",
                        "query": "Which page states the budget for copper?",
                        "relevant_pages": [1],
                    },
                    {
                        "id": "inventory",
                        "query": "Where is the warehouse inventory of computer monitors?",
                        "relevant_pages": [2],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root / "request.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    print(create(parser.parse_args().output, Settings()))
