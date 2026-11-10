"""Exercise the public workflow with the shipped synthetic PDF and an isolated cookie session."""

import argparse
import time
from pathlib import Path

import httpx


def verify(base: str) -> None:
    pdf = (
        Path(__file__).resolve().parents[1]
        / "public"
        / "sample"
        / "northline-field-report.pdf"
    )
    headers = {"X-Folio-Request": "1"}
    with (
        httpx.Client(base_url=base, timeout=90, headers=headers) as browser,
        httpx.Client(base_url=base, timeout=20) as stranger,
    ):
        assert browser.get("/").status_code == 200
        assert browser.get("/workspace-api/documents").json()["documents"] == []
        response = browser.post(
            "/workspace-api/documents",
            content=b"not a PDF",
            headers={"Content-Type": "application/pdf", "X-Filename": "invalid.pdf"},
        )
        assert response.status_code == 415
        response = browser.post(
            "/workspace-api/documents",
            content=pdf.read_bytes(),
            headers={
                "Content-Type": "application/pdf",
                "X-Filename": "northline-field-report.pdf",
            },
        )
        response.raise_for_status()
        doc = "/workspace-api/documents/" + response.json()["id"]
        try:
            assert stranger.get(doc).status_code == 404
            assert stranger.get(doc + "/pages/2").status_code == 404
            for _ in range(240):
                current = browser.get(doc).raise_for_status().json()
                if current["status"] == "error" or current["visualStatus"] == "partial":
                    raise AssertionError(current["error"] or current["warning"])
                if current["status"] == "ready" and current["visualCount"] == 4:
                    break
                time.sleep(2)
            assert current["total"] == 4 and current["visualCount"] == 4, current
            for query, mode, expected in [
                ("Where are the replacement monitors stored?", "text", 4),
                ("What is the procurement budget?", "hybrid", 2),
                ("Solar share of electricity by month", "visual", 3),
            ]:
                result = (
                    browser.post(doc + "/search", json={"query": query, "mode": mode})
                    .raise_for_status()
                    .json()
                )
                assert result["results"][0]["page"] == expected, result
                print(mode, "ranked page", expected, "first", flush=True)
            page = browser.get(doc + "/pages/4").raise_for_status()
            assert page.content.startswith(b"\x89PNG") and page.headers[
                "content-type"
            ].startswith("image/png")
            details = browser.get(doc + "/pages/4/details").raise_for_status().json()
            assert (
                "aisle seven" in details["text"].lower() and "ocr" in details["method"]
            )
            details = browser.get(doc + "/pages/2/details").raise_for_status().json()
            assert any("$480,000" in str(t["rows"]) for t in details["tables"])
        finally:
            browser.delete(doc).raise_for_status()
        assert browser.get(doc).status_code == 404
        print(
            "Verified upload, isolation, indexing, text, visual and hybrid ranking, OCR, tables, previews and deletion."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3108")
    verify(parser.parse_args().base_url)
