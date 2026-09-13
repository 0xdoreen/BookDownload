from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookdownload.models import BookRequest, BookStatus
from bookdownload.storage import QueueStore


class StorageTests(unittest.TestCase):
    def test_queue_persists_and_due_waits(self):
        with TemporaryDirectory() as directory:
            store = QueueStore(directory)
            ids = store.add_books(
                [BookRequest(title="Book", raw_text="Book")], Path(directory), Path(directory) / "list.txt"
            )
            future = datetime.now(UTC) + timedelta(hours=24)
            store.update_status(ids[0], BookStatus.QUOTA_WAIT, next_attempt_at=future)
            reopened = QueueStore(directory)
            self.assertEqual(BookStatus.QUOTA_WAIT.value, reopened.get(ids[0])["status"])
            self.assertEqual([], reopened.due_items())

    def test_remove_does_not_delete_result(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            downloaded = folder / "Book.pdf"
            downloaded.touch()
            store = QueueStore(folder / "state")
            item_id = store.add_books(
                [BookRequest(title="Book", raw_text="Book")], folder, folder / "list.txt"
            )[0]
            store.update_status(item_id, BookStatus.COMPLETED, result_path=downloaded)
            self.assertTrue(store.delete(item_id))
            self.assertTrue(downloaded.exists())


if __name__ == "__main__":
    unittest.main()
