from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .models import BookRequest, Candidate, MatchResult


EXCLUDED_MARKERS = {
    "summary",
    "study guide",
    "teacher edition",
    "teachers edition",
    "workbook",
    "sample",
    "excerpt",
    "abridged",
}


def normalize(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


def similarity(left: str | None, right: str | None) -> float:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_candidate(book: BookRequest, candidate: Candidate) -> MatchResult:
    reasons: list[str] = []
    blockers: list[str] = []
    candidate_text = normalize(f"{candidate.title} {candidate.edition or ''}")
    excluded = sorted(marker for marker in EXCLUDED_MARKERS if marker in candidate_text)
    if excluded:
        blockers.append(f"疑似非完整正文：{', '.join(excluded)}")

    if book.isbn and candidate.isbn:
        if normalize(book.isbn) == normalize(candidate.isbn):
            reasons.append("ISBN 完全一致")
            return MatchResult(candidate, 100.0, reasons, blockers)
        blockers.append("ISBN 冲突")

    title_ratio = similarity(book.title, candidate.title)
    author_ratio = similarity(book.author, candidate.author)
    series_ratio = similarity(book.series, candidate.series)
    volume_ratio = similarity(book.volume, candidate.volume)

    score = title_ratio * 35
    reasons.append(f"书名相似度 {title_ratio:.0%}")

    if book.author and candidate.author:
        score += author_ratio * 25
        reasons.append(f"作者相似度 {author_ratio:.0%}")
        if author_ratio < 0.45:
            blockers.append("作者冲突")
    elif book.author:
        reasons.append("候选缺少作者")

    if book.series or book.volume:
        series_component = (series_ratio + volume_ratio) / (bool(book.series) + bool(book.volume))
        score += series_component * 15
        reasons.append(f"系列/卷次相似度 {series_component:.0%}")
        if book.volume and candidate.volume and volume_ratio < 0.5:
            blockers.append("卷次冲突")
    else:
        score += 15

    if book.language and candidate.language:
        if normalize(book.language) == normalize(candidate.language):
            score += 10
            reasons.append("语言一致")
        else:
            blockers.append("语言冲突")
    else:
        score += 5

    if book.publication_year and candidate.publication_year:
        score += 5 if book.publication_year == candidate.publication_year else 2
    else:
        score += 2.5

    if candidate.complete and not candidate.quality_warning:
        score += 10
        reasons.append("未发现完整性或质量警告")
    elif candidate.complete:
        score += 4
        reasons.append(f"质量警告：{candidate.quality_warning}")
    else:
        blockers.append("候选可能不完整")

    return MatchResult(candidate, round(min(score, 100), 2), reasons, blockers)


def rank_candidates(book: BookRequest, candidates: list[Candidate]) -> list[MatchResult]:
    results = [score_candidate(book, candidate) for candidate in candidates]
    return sorted(results, key=_rank_key, reverse=True)


def _rank_key(result: MatchResult) -> tuple[float, int, int, int]:
    candidate = result.candidate
    safe = 0 if result.blockers else 1
    year = candidate.publication_year or 0
    pdf = 1 if normalize(candidate.file_format) == "pdf" else 0
    return safe, result.score, year, pdf
