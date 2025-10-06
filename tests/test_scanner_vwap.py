import unittest

from arbitrage.scanner import vwap_price_from_orderbook, find_executable_opportunities
from arbitrage.exchanges.mock_exchange import MockExchange


class VWAPTests(unittest.TestCase):
    def test_vwap_simple(self):
        # asks: prices increasing, sizes
        asks = [(100.0, 1.0), (101.0, 2.0), (102.0, 5.0)]
        price = vwap_price_from_orderbook(asks, 2.0)
        # expected: fill 1@100 + 1@101 => total cost 100 + 101 = 201 => avg 100.5
        self.assertAlmostEqual(price, 100.5)

    def test_vwap_insufficient(self):
        asks = [(100.0, 0.5), (101.0, 0.4)]
        price = vwap_price_from_orderbook(asks, 2.0)
        self.assertIsNone(price)


class ExecutableScannerTests(unittest.TestCase):
    def test_find_executable_opportunities_mock(self):
        # two mock exchanges with different prices
        ex1 = MockExchange("A", {"FOO-USD": 100.0})
        ex2 = MockExchange("B", {"FOO-USD": 102.0})
        opps = find_executable_opportunities([ex1, ex2], amount=1.0, min_profit_pct=0.1)
        self.assertTrue(len(opps) >= 1)
        top = opps[0]
        self.assertEqual(top.buy_exchange, "A")
        self.assertEqual(top.sell_exchange, "B")


if __name__ == "__main__":
    unittest.main()
