from pprint import pprint
import os, sys
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage.exchanges.mock_exchange import MockExchange
from arbitrage.scanner import vwap_price_from_orderbook

ex1 = MockExchange('A', {'FOO-USD': 100.0})
ex2 = MockExchange('B', {'FOO-USD': 102.0})
exs = [ex1, ex2]

market = {}
for ex in exs:
    tk = ex.get_tickers()['FOO-USD']
    ts = getattr(tk, 'timestamp', None)
    market.setdefault('FOO-USD', []).append((ex, ex.name, float(tk.price), ts))

print('market:', market)

for sym, quotes in market.items():
    for i in range(len(quotes)):
        for j in range(len(quotes)):
            if i == j:
                continue
            buy_obj, buy_ex, buy_price, buy_ts = quotes[i]
            sell_obj, sell_ex, sell_price, sell_ts = quotes[j]
            print('\npair:', buy_ex, '->', sell_ex)
            print('  buy_price', buy_price, 'sell_price', sell_price)
            raw_diff_pct = (sell_price - buy_price) / buy_price * 100.0 if buy_price > 0 else 0.0
            print('  raw_diff_pct', raw_diff_pct)
            buy_fee = getattr(buy_obj, 'fee_rate', 0.0)
            sell_fee = getattr(sell_obj, 'fee_rate', 0.0)
            print('  fees', buy_fee, sell_fee)
            effective_buy = buy_price * (1.0 + buy_fee)
            effective_sell = sell_price * (1.0 - sell_fee)
            print('  effective_buy', effective_buy, 'effective_sell', effective_sell)
            # check orderbook fallback
            ob = buy_obj.get_order_book('FOO-USD')
            print('  buy ob asks[0]', ob['asks'][:3])
            vwap = vwap_price_from_orderbook(ob['asks'], 1.0)
            print('  buy vwap 1.0 ->', vwap)
            ob2 = sell_obj.get_order_book('FOO-USD')
            print('  sell ob bids[0]', ob2['bids'][:3])
            vwap2 = vwap_price_from_orderbook(ob2['bids'], 1.0)
            print('  sell vwap 1.0 ->', vwap2)

print('\ndone')
