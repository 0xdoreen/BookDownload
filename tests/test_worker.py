from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookdownload.channels import QuotaExceeded
from bookdownload.models import BookRequest, BookStatus
from bookdownload.storage import QueueStore
from bookdownload.worker import QueueWorker


class QuotaChannel:
    def search(self, book):
        raise QuotaExceeded("额度已用完")

    def download(self, candidate, destination):
        raise AssertionError("不应下载")


class WorkerTests(unittest.TestCase):
    def test_quota_defers_current_and_remaining_items(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            store = QueueStore(folder / "state")
            ids = store.add_books(
                [BookRequest(title=f"Book {index}", raw_text="") for index in range(2)],
                folder,
                folder / "list.txt",
            )
            worker = QueueWorker(store, QuotaChannel())
            self.assertEqual(1, worker.run_once())
            for item_id in ids:
                row = store.get(item_id)
                self.assertEqual(BookStatus.QUOTA_WAIT.value, row["status"])
                due = datetime.fromisoformat(row["next_attempt_at"])
                self.assertGreater(due, datetime.now(UTC) + timedelta(hours=23))


if __name__ == "__main__":
    unittest.main()
