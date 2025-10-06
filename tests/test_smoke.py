import os
import sys
import unittest

# Ensure the project's src/ directory is on sys.path so tests can import the package
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage import cli


class SmokeTest(unittest.TestCase):
    def test_fetch_prices_has_entries(self):
        prices = cli.fetch_prices()
        self.assertIsInstance(prices, dict)
        self.assertTrue(len(prices) > 0)


if __name__ == "__main__":
    unittest.main()
