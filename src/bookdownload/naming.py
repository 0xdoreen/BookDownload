from __future__ import annotations

import re
from pathlib import Path

from .models import BookRequest


SITE_SUFFIX = re.compile(
    r"\s*[([]\s*(?=[^\])]*(?:z-library|z-lib|1lib))[^\])]*[)\]]\s*$",
    re.IGNORECASE,
)
INVALID_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_site_suffix(stem: str) -> str:
    previous = None
    current = stem.strip()
    while previous != current:
        previous = current
        current = SITE_SUFFIX.sub("", current).strip(" .-_")
    return current


def build_filename(book: BookRequest, extension: str, max_length: int = 220) -> str:
    parts = [book.series, book.author, book.title, book.volume]
    if book.language == "en":
        if book.lexile:
            value = f"~{book.lexile}" if book.lexile_estimated else book.lexile
            parts.append(f"[Lexile {value}]")
        if book.ar is not None:
            value = f"~{book.ar:g}" if book.ar_estimated else f"{book.ar:g}"
            parts.append(f"[AR {value}]")
    stem = " - ".join(str(part).strip() for part in parts if part and str(part).strip())
    stem = INVALID_WINDOWS.sub("_", stem)
    stem = re.sub(r"\s+", " ", stem).rstrip(" .")
    suffix = "." + extension.lower().lstrip(".")
    allowed = max(1, max_length - len(suffix))
    return stem[:allowed].rstrip(" .-") + suffix


def available_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    index = 2
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1
