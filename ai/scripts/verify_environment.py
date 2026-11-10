import json
import platform
import shutil
from importlib.metadata import PackageNotFoundError, version

import pytesseract

from src.models.registry import hardware


def report() -> dict:
    packages = {}
    for p in (
        "fastapi",
        "pymupdf",
        "pytesseract",
        "torch",
        "sentence-transformers",
        "colpali-engine",
        "boto3",
    ):
        try:
            packages[p] = version(p)
        except PackageNotFoundError:
            packages[p] = None
    return {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "tesseract_languages": pytesseract.get_languages() if shutil.which("tesseract") else [],
        "compute": hardware(),
        "packages": packages,
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
