from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .channels import AccessBlocked, AddressInvalid, DownloadChannel, LoginRequired, QuotaExceeded
from .matcher import rank_candidates
from .models import BookStatus
from .naming import available_path, build_filename
from .storage import QueueStore, row_to_book


class QueueWorker:
    def __init__(self, store: QueueStore, channel: DownloadChannel, quota_wait_hours: int = 24):
        self.store = store
        self.channel = channel
        self.quota_wait_hours = quota_wait_hours

    def run_once(self) -> int:
        processed = 0
        for row in self.store.due_items():
            processed += 1
            item_id = row["id"]
            book = row_to_book(row)
            try:
                self.store.update_status(item_id, BookStatus.SEARCHING, increment_attempts=True)
                candidates = self.channel.search(book)
                ranked = rank_candidates(book, candidates)
                if not ranked:
                    self.store.update_status(item_id, BookStatus.NOT_FOUND, error="没有找到候选资源")
                    continue
                best = ranked[0]
                if best.requires_review:
                    detail = json.dumps(
                        {"score": best.score, "reasons": best.reasons, "blockers": best.blockers},
                        ensure_ascii=False,
                    )
                    self.store.update_status(item_id, BookStatus.REVIEW_REQUIRED, error=detail)
                    continue
                candidate = best.candidate
                extension = (candidate.file_format or "bin").lower()
                output_dir = Path(row["output_dir"])
                output_dir.mkdir(parents=True, exist_ok=True)
                target = available_path(output_dir, build_filename(book, extension))
                self.store.update_status(item_id, BookStatus.DOWNLOADING)
                downloaded = self.channel.download(candidate, target)
                self.store.update_status(item_id, BookStatus.COMPLETED, result_path=downloaded)
            except QuotaExceeded as exc:
                due = datetime.now(UTC) + timedelta(hours=self.quota_wait_hours)
                self.store.update_status(item_id, BookStatus.QUOTA_WAIT, error=str(exc), next_attempt_at=due)
                self._defer_remaining(due)
                break
            except LoginRequired as exc:
                self.store.update_status(item_id, BookStatus.LOGIN_REQUIRED, error=str(exc))
                self._mark_remaining(BookStatus.LOGIN_REQUIRED, str(exc))
                break
            except (AddressInvalid, AccessBlocked) as exc:
                self.store.update_status(item_id, BookStatus.PAUSED, error=str(exc))
                self._mark_remaining(BookStatus.PAUSED, str(exc))
                break
            except Exception as exc:  # keep one item from losing the remaining queue
                self.store.update_status(item_id, BookStatus.FAILED, error=str(exc))
        return processed

    def run_forever(self, poll_seconds: int = 30) -> None:
        while True:
            processed = self.run_once()
            if processed == 0:
                next_due = self.store.next_due_at()
                wait = poll_seconds
                if next_due:
                    wait = max(1, min(poll_seconds, int((next_due - datetime.now(UTC)).total_seconds())))
                time.sleep(wait)

    def _defer_remaining(self, due: datetime) -> None:
        for row in self.store.due_items():
            if row["status"] in (BookStatus.PENDING.value, BookStatus.READY.value):
                self.store.update_status(
                    row["id"], BookStatus.QUOTA_WAIT, error="等待账号额度恢复", next_attempt_at=due
                )

    def _mark_remaining(self, status: BookStatus, error: str) -> None:
        for row in self.store.due_items():
            if row["status"] in (BookStatus.PENDING.value, BookStatus.READY.value):
                self.store.update_status(row["id"], status, error=error)
