from pathlib import Path
import unittest

from bookdownload.parser import parse_booklist, parse_text


ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_parses_sample_without_headings_or_descriptions(self):
        books = parse_booklist(ROOT / "示例1.txt")
        self.assertEqual(30, len(books))
        self.assertEqual("The Explorer", books[0].title)
        self.assertEqual("Katherine Rundell", books[0].author)
        self.assertEqual("740L", books[0].lexile)
        self.assertEqual(5.4, books[0].ar)
        self.assertEqual("Katherine Rundell", books[1].author)
        pony = next(book for book in books if book.title == "Pony")
        self.assertEqual("R.J. Palacio", pony.author)

    def test_splits_nested_series_books(self):
        books = parse_booklist(ROOT / "示例1.txt")
        titles = [book.title for book in books]
        self.assertIn("The School for Thieves", titles)
        self.assertIn("The Thieves' Revenge", titles)
        self.assertIn("Island Heist", titles)
        nested = next(book for book in books if book.title == "Island Heist")
        self.assertEqual("Crookhaven", nested.series)
        self.assertTrue(nested.lexile_estimated)

    def test_utf8_bom_and_chinese_title(self):
        books = parse_text("1. **Rooftoppers《屋顶上的索菲》**（Katherine Rundell）\nAR：5.0｜Lexile：700L")
        self.assertEqual("Rooftoppers", books[0].title)
        self.assertEqual("屋顶上的索菲", books[0].translated_title)


if __name__ == "__main__":
    unittest.main()
