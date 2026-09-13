from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookdownload.models import BookRequest
from bookdownload.naming import available_path, build_filename, clean_site_suffix


class NamingTests(unittest.TestCase):
    def test_cleans_known_site_suffix(self):
        value = "The Explorer (z-library.sk, 1lib.sk, z-lib.sk)"
        self.assertEqual("The Explorer", clean_site_suffix(value))

    def test_builds_requested_order_and_estimate_markers(self):
        book = BookRequest(
            title="The School for Thieves",
            author="J.J. Arcanjo",
            series="Crookhaven",
            volume="Book 1",
            language="en",
            lexile="750L",
            lexile_estimated=True,
            ar=5.1,
            ar_estimated=True,
            raw_text="",
        )
        self.assertEqual(
            "Crookhaven - J.J. Arcanjo - The School for Thieves - Book 1 - [Lexile ~750L] - [AR ~5.1].pdf",
            build_filename(book, "PDF"),
        )

    def test_avoids_overwrite(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "Book.pdf").touch()
            self.assertEqual(folder / "Book (2).pdf", available_path(folder, "Book.pdf"))


if __name__ == "__main__":
    unittest.main()
