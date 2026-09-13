import unittest

from bookdownload.models import BookRequest
from bookdownload.review import apply_review_command


class ReviewTests(unittest.TestCase):
    def test_edit_and_delete(self):
        books = [BookRequest(title="One", raw_text=""), BookRequest(title="Two", raw_text="")]
        apply_review_command(books, "edit 1 author=Writer")
        self.assertEqual("Writer", books[0].author)
        apply_review_command(books, "delete 2")
        self.assertEqual(["One"], [book.title for book in books])

    def test_split(self):
        books = [BookRequest(title="Series", series="S", raw_text="")]
        apply_review_command(books, "split 1 First | Second")
        self.assertEqual(["First", "Second"], [book.title for book in books])
        self.assertEqual("S", books[1].series)

    def test_merge_fills_missing_metadata(self):
        books = [
            BookRequest(title="Book", raw_text="left"),
            BookRequest(title="Duplicate", author="Writer", raw_text="right"),
        ]
        apply_review_command(books, "merge 1 2")
        self.assertEqual(1, len(books))
        self.assertEqual("Writer", books[0].author)


if __name__ == "__main__":
    unittest.main()
