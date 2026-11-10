from io import BytesIO

import pymupdf
from PIL import Image

NATIVE = "Quarterly revenue reached forty million dollars."
SCAN = "Warehouse inventory contains fifty monitors."


def scan(fmt="PNG"):
    with pymupdf.open() as doc:
        page = doc.new_page(width=520, height=130)
        page.insert_text((15, 70), SCAN, fontsize=19)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        with BytesIO() as stream:
            image.save(stream, fmt)
            return stream.getvalue()


def pdf(kinds=("native",)):
    with pymupdf.open() as doc:
        for kind in kinds:
            page = doc.new_page(width=550, height=480)
            if kind in ("native", "mixed", "columns", "chart", "table"):
                page.insert_text((25, 85), NATIVE)
            if kind in ("scanned", "mixed"):
                page.insert_image(pymupdf.Rect(12, 120, 532, 250), stream=scan())
            if kind == "columns":
                page.insert_text((300, 85), "Right column")
            if kind == "table":
                for x in (30, 160, 290):
                    page.draw_line((x, 150), (x, 230))
                for y in (150, 190, 230):
                    page.draw_line((30, y), (290, y))
                for y, row in [(175, ("Team", "Budget")), (215, ("Finance", "5000"))]:
                    for x, value in zip((40, 170), row):
                        page.insert_text((x, y), value)
            if kind == "chart":
                page.draw_rect((50, 200, 85, 260), fill=(0, 0, 1))
                page.draw_rect((110, 150, 145, 260), fill=(0, 1, 0))
                page.insert_text((35, 290), "Figure 1. Revenue by quarter")
        return doc.tobytes()
