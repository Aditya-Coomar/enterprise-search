from collections.abc import Callable
from typing import Protocol

import pymupdf

from src.schemas.contracts import Box, Table


class TableExtractor(Protocol):
    def __call__(self, page: pymupdf.Page, page_id: str, box: Callable[..., Box]) -> list[Table]: ...


def ruled_tables(page: pymupdf.Page, page_id: str, box: Callable[..., Box]) -> list[Table]:
    tables = []
    for index, table in enumerate(page.find_tables().tables, 1):
        rows = [[cell or "" for cell in row] for row in table.extract()]
        tables.append(
            Table(
                table_id=f"{page_id}-t{index}",
                page_number=page.number + 1,
                bbox=box(table.bbox),
                rows=rows,
                columns=table.col_count,
                text="\n".join(" | ".join(row) for row in rows),
            )
        )
    return tables
