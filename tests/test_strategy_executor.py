import os
import unittest

from arbitrage.strategy_executor import StrategyExecutor


class StrategyExecutorTests(unittest.TestCase):
    def test_run_dry_from_signals_if_available(self):
        csv = os.path.join('var', 'bear_verbose_alpine_signals.csv')
        if not os.path.exists(csv):
            self.skipTest('signals CSV not present: ' + csv)
        se = StrategyExecutor(mode='dry')
        res = se.run_from_signals_file(csv, run_id='test-dry')
        self.assertIn('run_id', res)
        self.assertIn('trace_path', res)
        self.assertGreaterEqual(res.get('events', 0), 0)


if __name__ == '__main__':
    unittest.main()
