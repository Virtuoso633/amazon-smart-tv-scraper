# tests/test_scraper.py

import unittest
from scraper.scraper import clean_text

class TestUtils(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  Hello   World\n"), "Hello World")

if __name__ == "__main__":
    unittest.main()
