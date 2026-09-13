from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BookStatus(StrEnum):
    PENDING = "pending"
    SEARCHING = "searching"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PAUSED = "paused"
    QUOTA_WAIT = "quota_wait"
    LOGIN_REQUIRED = "login_required"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class BookRequest:
    title: str
    raw_text: str
    translated_title: str | None = None
    author: str | None = None
    series: str | None = None
    volume: str | None = None
    language: str | None = None
    isbn: str | None = None
    publication_year: int | None = None
    edition: str | None = None
    ar: float | None = None
    ar_estimated: bool = False
    lexile: str | None = None
    lexile_estimated: bool = False
    notes: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Candidate:
    title: str
    author: str | None = None
    series: str | None = None
    volume: str | None = None
    language: str | None = None
    isbn: str | None = None
    publication_year: int | None = None
    edition: str | None = None
    file_format: str | None = None
    file_size: int | None = None
    pages: int | None = None
    complete: bool = True
    quality_warning: str | None = None
    detail_url: str | None = None
    download_url: str | None = None


@dataclass(slots=True)
class MatchResult:
    candidate: Candidate
    score: float
    reasons: list[str]
    blockers: list[str]

    @property
    def requires_review(self) -> bool:
        return self.score < 90 or bool(self.blockers)
