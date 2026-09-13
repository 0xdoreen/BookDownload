from __future__ import annotations

import re
from pathlib import Path

from .models import BookRequest


NUMBERED = re.compile(
    r"^\s*\d+[.)、]\s*\*\*(?P<bold>.+?)\*\*\s*(?P<tail>[（(].*?[）)])?\s*$"
)
INNER_TITLE = re.compile(r"^\s*《([^》]+)》\s*$")
METRICS = re.compile(
    r"AR\s*[：:]\s*(?:【?估算\s*)?(?P<ar>\d+(?:\.\d+)?)】?"
    r"\s*[｜|]\s*Lexile\s*[：:]\s*(?P<lexile>\d+L)",
    re.IGNORECASE,
)
CN_TITLE = re.compile(r"《([^》]+)》")
PARENS = re.compile(r"[（(]([^）)]+)[）)]")
ISBN = re.compile(r"ISBN(?:-1[03])?\s*[：:]?\s*([0-9Xx-]{10,17})")


def parse_booklist(path: str | Path) -> list[BookRequest]:
    return parse_text(Path(path).read_text(encoding="utf-8-sig"))


def parse_text(text: str) -> list[BookRequest]:
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if NUMBERED.match(line):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            if line.lstrip().startswith("## "):
                blocks.append(current)
                current = []
            else:
                current.append(line)
    if current:
        blocks.append(current)

    books: list[BookRequest] = []
    for block in blocks:
        books.extend(_parse_block(block))
    return books


def _parse_block(lines: list[str]) -> list[BookRequest]:
    header_match = NUMBERED.match(lines[0])
    if not header_match:
        return []
    header = "".join(part for part in (header_match.group("bold"), header_match.group("tail")) if part).strip()
    inner_positions = [i for i, line in enumerate(lines) if INNER_TITLE.match(line)]
    if inner_positions:
        series = _series_from_header(header)
        result: list[BookRequest] = []
        for pos_idx, start in enumerate(inner_positions):
            end = inner_positions[pos_idx + 1] if pos_idx + 1 < len(inner_positions) else len(lines)
            title = INNER_TITLE.match(lines[start]).group(1).strip()  # type: ignore[union-attr]
            segment = lines[start:end]
            result.append(_make_book(title, segment, series=series))
        return result
    return [_make_book(header, lines)]


def _make_book(header: str, lines: list[str], series: str | None = None) -> BookRequest:
    original_header = header
    parens = PARENS.findall(original_header)
    title_part = PARENS.sub("", original_header).strip()
    translated = None
    cn_match = CN_TITLE.search(title_part)
    if cn_match:
        translated = cn_match.group(1).strip()
        title_part = CN_TITLE.sub("", title_part).strip()

    author = None
    for value in parens:
        if not _looks_like_series(value):
            author = _clean_author(value)
            break
    if series is None:
        for value in parens:
            if _looks_like_series(value):
                series = re.sub(r"\s*(?:盗贼学校)?系列\s*$", "", value).strip()

    joined = "\n".join(lines)
    metric_match = METRICS.search(joined)
    estimated = bool(re.search(r"AR\s*[：:].{0,4}估算", joined, re.IGNORECASE))
    isbn_match = ISBN.search(joined)
    notes = _extract_notes(lines)
    warnings: list[str] = []
    if not author:
        warnings.append("缺少作者")

    return BookRequest(
        title=title_part.strip(" ：:"),
        raw_text=joined.strip(),
        translated_title=translated,
        author=author,
        series=series,
        language=_infer_language(title_part),
        isbn=isbn_match.group(1).replace("-", "") if isbn_match else None,
        ar=float(metric_match.group("ar")) if metric_match else None,
        ar_estimated=estimated and metric_match is not None,
        lexile=metric_match.group("lexile").upper() if metric_match else None,
        lexile_estimated=estimated and metric_match is not None,
        notes=notes,
        warnings=warnings,
    )


def _extract_notes(lines: list[str]) -> str | None:
    candidates = []
    for line in lines[1:]:
        value = line.strip()
        if not value or INNER_TITLE.match(value) or METRICS.search(value):
            continue
        candidates.append(value)
    return " ".join(candidates) or None


def _series_from_header(header: str) -> str:
    parens = PARENS.findall(header)
    if parens:
        value = re.sub(r"\s*(?:盗贼学校)?系列\s*$", "", parens[0]).strip()
        return value
    return CN_TITLE.sub("", PARENS.sub("", header)).strip()


def _looks_like_series(value: str) -> bool:
    lowered = value.casefold()
    return "系列" in value or "series" in lowered or "crookhaven" in lowered


def _clean_author(value: str) -> str:
    value = CN_TITLE.sub("", value)
    value = re.sub(r"(?:作者|卡内基(?:文学奖|金奖)?)\s*$", "", value)
    value = value.split("，", 1)[0]
    return value.strip(" ,，")


def _infer_language(title: str) -> str:
    return "zh" if re.search(r"[\u3400-\u9fff]", title) else "en"
