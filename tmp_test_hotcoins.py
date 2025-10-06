from arbitrage.exchanges.mock_exchange import MockExchange
from arbitrage.hotcoins import find_hot_coins, _cum_depth_usd_from_orderbook

def main():
    # Create mock exchanges with divergent prices for a hot symbol
    ex_a = MockExchange('A', {'HOT-USD': 100.0, 'BTC-USD': 50000.0}, depth=5.0)
    ex_b = MockExchange('B', {'HOT-USD': 102.5, 'BTC-USD': 49900.0}, depth=6.0)
    ex_c = MockExchange('C', {'HOT-USD': 99.0, 'BTC-USD': 50050.0}, depth=2.0)

    exchanges = [ex_a, ex_b, ex_c]
    # print orderbooks and depth per exchange
    for ex in exchanges:
        ob = ex.get_order_book('HOT-USD')
        print(f'Exchange {ex.name} orderbook sample: asks[0]={ob.get("asks",[])[0] if ob.get("asks") else None} bids[0]={ob.get("bids",[])[0] if ob.get("bids") else None}')
        bd = _cum_depth_usd_from_orderbook(ob, 'bids', price_band_pct=0.5)
        ad = _cum_depth_usd_from_orderbook(ob, 'asks', price_band_pct=0.5)
        print(f'  bids_depth_usd={bd:.2f} asks_depth_usd={ad:.2f}')

    results = find_hot_coins(exchanges, spread_threshold_pct=0.5, min_depth_usd=100.0)
    print('\nFound', len(results), 'hot coins')
    for r in results:
        print(r)

if __name__ == '__main__':
    main()
from arbitrage.exchanges.mock_exchange import MockExchange
from arbitrage.hotcoins import find_hot_coins

def main():
    # Create mock exchanges with divergent prices for a hot symbol
    ex_a = MockExchange('A', {'HOT-USD': 100.0, 'BTC-USD': 50000.0}, depth=5.0)
    ex_b = MockExchange('B', {'HOT-USD': 102.5, 'BTC-USD': 49900.0}, depth=6.0)
    ex_c = MockExchange('C', {'HOT-USD': 99.0, 'BTC-USD': 50050.0}, depth=2.0)

    results = find_hot_coins([ex_a, ex_b, ex_c], spread_threshold_pct=0.5, min_depth_usd=100.0)
    print('Found', len(results), 'hot coins')
    for r in results:
        print(r)

if __name__ == '__main__':
    main()
