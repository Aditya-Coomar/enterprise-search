"""Build the public, fictional field report used by the interactive PDF workspace."""

import math
from pathlib import Path

import pymupdf as pdf

out = Path(__file__).resolve().parents[1] / "public" / "sample"
ink = (0.10, 0.14, 0.22)
blue = (0.12, 0.26, 0.82)
paper = (0.97, 0.96, 0.92)
doc = pdf.open()


def text(page, x, y, value, size=12, color=ink, font="helv"):
    page.insert_text((x, y), value, fontsize=size, fontname=font, color=color)


def page(n, title):
    p = doc.new_page(width=480, height=625)
    p.draw_rect(p.rect, color=None, fill=paper)
    text(p, 34, 36, "NORTHLINE   /   RESEARCH OFFICE", 9)
    text(p, 395, 36, f"0{n} / 04", 9)
    p.draw_line((34, 48), (446, 48), color=ink, width=0.65)
    text(p, 34, 107, title, 30, font="tiro")
    return p


p = doc.new_page(width=480, height=625)
p.draw_rect(p.rect, color=None, fill=blue)
white = (1, 1, 1)
text(p, 32, 37, "N O R T H L I N E", 13, white, "hebo")
text(p, 348, 37, "RESEARCH OFFICE", 9, white)
p.draw_line((32, 53), (448, 53), color=white, width=0.6)
text(p, 32, 105, "OPERATIONS  /  2026", 11, white)
text(p, 28, 182, "Field", 79, white, "tiro")
text(p, 28, 254, "Report", 79, white, "tiro")
for i in range(48):
    pts = []
    for j in range(97):
        x = j * 5
        y = (
            350
            + i * 3.3
            + 53 * math.sin(x / 106 + i * 0.029)
            + 15 * math.cos(x / 55 - i * 0.065)
        )
        pts.append((x, y))
    p.draw_polyline(pts, color=(0.62, 0.77, 0.99), width=0.6)
text(p, 32, 589, "Procurement, energy and site logistics", 12, white)
text(p, 370, 589, "VOL. 01", 10, white)
p = page(2, "Procurement budget")
text(p, 34, 154, "The approved procurement budget is $480,000.", 16)
text(p, 34, 189, "Capital allocation for the Northline field program in 2026:")
rows = [
    ("Category", "Allocation"),
    ("Site equipment", "$220,000"),
    ("Transport and freight", "$160,000"),
    ("Monitoring instruments", "$100,000"),
    ("Total", "$480,000"),
]
for i, (label, value) in enumerate(rows):
    y = 230 + i * 42
    p.draw_line((34, y), (446, y), color=ink, width=0.6)
    text(p, 45, y + 26, label, 13, font="hebo" if i == 0 else "helv")
    text(p, 316, y + 26, value, 13)
p.draw_line((34, 440), (446, 440), color=ink)
for x in (34, 305, 446):
    p.draw_line((x, 230), (x, 440), color=ink, width=0.6)
text(p, 34, 493, "Finance owner: Mara Chen. Approved on 14 September 2026.", 12)
p = page(3, "Energy consumption")
text(p, 34, 150, "Solar generation supplied 68% of site electricity in August.", 14)
text(p, 34, 194, "Solar share of electricity use by month", 13, font="hebo")
for i, (month, v) in enumerate(
    [("May", 38), ("June", 47), ("July", 55), ("August", 68)]
):
    x = 66 + i * 91
    top = 432 - v * 2.8
    p.draw_rect((x, top, x + 53, 432), color=None, fill=blue)
    text(p, x, top - 10, str(v) + "%", 12)
    text(p, x, 455, month)
p.draw_line((43, 433), (440, 433), color=ink)
text(p, 34, 520, "The battery upgrade reduced diesel generator operating hours.", 12)
with pdf.open() as draft:
    q = draft.new_page(width=480, height=625)
    text(
        q,
        35,
        44,
        "NORTHLINE  /  FIELD LOG                                     04 / 04",
        11,
    )
    text(q, 35, 112, "Warehouse inventory", 31, font="tiro")
    text(q, 35, 171, "Receiving log - East warehouse", 16, font="hebo")
    for y, line in enumerate(
        [
            "Fifty replacement monitors arrived on 18 September.",
            "The monitors are stored in the east warehouse, aisle seven.",
            "The next inspection is scheduled for 2 October.",
            "Shift supervisor: Priya Shah.",
        ]
    ):
        text(q, 35, 230 + y * 44, line, 13)
    image = q.get_pixmap(matrix=pdf.Matrix(1.8, 1.8)).tobytes("png")
p = doc.new_page(width=480, height=625)
p.insert_image(p.rect, stream=image)
doc.set_metadata(
    {
        "title": "Northline Field Report",
        "author": "Folio sample library",
        "subject": "Fictional demonstration report",
    }
)
doc.save(out / "northline-field-report.pdf", deflate=True, no_new_id=True)
for index in (0, 1, 2):
    doc[index].get_pixmap(matrix=pdf.Matrix(0.8, 0.8)).save(
        out / f"page-{index + 1}.png"
    )
doc.close()
