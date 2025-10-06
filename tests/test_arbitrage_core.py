import os
import sys
import unittest

# Ensure src/ on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage.exchanges.mock_exchange import MockExchange
from arbitrage.scanner import find_opportunities
from arbitrage.executor import Executor


class CoreTests(unittest.TestCase):
    def test_find_opportunity_and_dry_run_execute(self):
        ex1 = MockExchange("A", {"FOO-USD": 100.0})
        ex2 = MockExchange("B", {"FOO-USD": 102.0})
        opps = find_opportunities([ex1, ex2], min_profit_pct=0.1)
        self.assertTrue(len(opps) >= 1)
        top = opps[0]
        self.assertEqual(top.buy_exchange, "A")
        self.assertEqual(top.sell_exchange, "B")

        executor = Executor([ex1, ex2])
        res = executor.execute(top, amount=1.0, dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertIsNotNone(res["buy_order"]) and isinstance(res["buy_order"], dict)

    def test_execute_real_orders_on_mock(self):
        ex1 = MockExchange("A", {"FOO-USD": 100.0})
        ex2 = MockExchange("B", {"FOO-USD": 110.0})
        opps = find_opportunities([ex1, ex2], min_profit_pct=0.1)
        executor = Executor([ex1, ex2])
        res = executor.execute(opps[0], amount=0.5, dry_run=False)
        # mock exchanges should have recorded orders
        self.assertIsInstance(res["buy_order"], str)
        self.assertIsInstance(res["sell_order"], str)
        self.assertEqual(len(ex1.orders) + len(ex2.orders), 2)


if __name__ == "__main__":
    unittest.main()
