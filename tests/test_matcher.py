import unittest

from bookdownload.matcher import rank_candidates, score_candidate
from bookdownload.models import BookRequest, Candidate


class MatcherTests(unittest.TestCase):
    def setUp(self):
        self.book = BookRequest(title="The Explorer", author="Katherine Rundell", raw_text="")

    def test_exact_candidate_scores_high(self):
        candidate = Candidate(
            title="The Explorer", author="Katherine Rundell", language="en", file_format="PDF"
        )
        result = score_candidate(self.book, candidate)
        self.assertGreaterEqual(result.score, 90)
        self.assertFalse(result.blockers)

    def test_author_conflict_requires_review(self):
        candidate = Candidate(title="The Explorer", author="Someone Else", language="en")
        result = score_candidate(self.book, candidate)
        self.assertIn("作者冲突", result.blockers)

    def test_newer_epub_beats_older_pdf(self):
        older_pdf = Candidate(title="The Explorer", author="Katherine Rundell", publication_year=2020, file_format="PDF")
        newer_epub = Candidate(title="The Explorer", author="Katherine Rundell", publication_year=2024, file_format="EPUB")
        ranked = rank_candidates(self.book, [older_pdf, newer_epub])
        self.assertEqual("EPUB", ranked[0].candidate.file_format)

    def test_pdf_wins_for_same_version(self):
        epub = Candidate(title="The Explorer", author="Katherine Rundell", publication_year=2024, file_format="EPUB")
        pdf = Candidate(title="The Explorer", author="Katherine Rundell", publication_year=2024, file_format="PDF")
        ranked = rank_candidates(self.book, [epub, pdf])
        self.assertEqual("PDF", ranked[0].candidate.file_format)


if __name__ == "__main__":
    unittest.main()
