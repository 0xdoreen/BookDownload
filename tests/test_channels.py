import unittest

from bookdownload.channels import DEFAULT_SELECTORS, _parse_size


class ChannelTests(unittest.TestCase):
    def test_builtin_selectors_cover_search_and_download(self):
        required = {"search_input", "search_submit", "result", "result_title", "result_link", "download_link"}
        self.assertFalse(required - DEFAULT_SELECTORS.keys())

    def test_parse_file_size(self):
        self.assertEqual(2_600_468, _parse_size("2.48 MB"))
        self.assertEqual(249_856, _parse_size("244 KB"))


if __name__ == "__main__":
    unittest.main()
