#!/usr/bin/env python3
"""Run preview-hedge across multiple symbols and candidate exchanges using ccxt (standalone).

Usage: python tools/batch_preview_hedge.py
"""
from __future__ import annotations
import ccxt, time, json, urllib.request, urllib.parse, ssl

BINANCE_FUND_API = 'https://fapi.binance.com/fapi/v1/fundingRate'

def find_market(exchange, token):
    token = token.upper()
    markets = exchange.load_markets()
    if token in markets:
        return markets[token]['id'], markets[token]['symbol']
    for s, meta in markets.items():
        if token.replace('/', '') in s.replace('/', ''):
            return meta['id'], meta['symbol']
    return None, None

def simulate_from_orderbook(book_side, notional):
    rem = notional; cost = 0.0; filled = 0.0; levels = 0
    for p, q in book_side:
        p = float(p); q = float(q)
        lvl = p * q
        if rem <= 0: break
        take = min(rem, lvl)
        qty = take / p
        cost += qty * p; filled += qty; rem -= take; levels += 1
    return cost, filled, levels

def fetch_binance_funding(symbol):
    now_ms = int(time.time()*1000)
    start_ms = now_ms - 24*3600*1000
    q = urllib.parse.urlencode({'symbol': symbol.replace('/','').split(':')[0], 'startTime': str(start_ms), 'endTime': str(now_ms), 'limit':1000})
    url = BINANCE_FUND_API + '?' + q
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf8'))
            total = sum(float(r.get('fundingRate') or 0.0) for r in data)
            avg = total / len(data) if data else 0.0
            return len(data), total, avg
    except Exception:
        return 0, 0.0, 0.0

def main():
    symbols = ['MYX/USDT','RED/USDT','SOMI/USDT','BAKE/USDT','ZKC/USDT','HIFI/USDT','MUSDT/USDT','SUPER/USDT','2Z/USDT','0G/USDT']
    candidates = ['mexc','kucoin','gate','okx','huobi']
    out = {}
    binance = ccxt.binance({'enableRateLimit': True})
    exchanges = {}
    for k in candidates:
        try:
            ctor = ccxt.__dict__.get(k)
            exchanges[k] = ctor({'enableRateLimit': True}) if ctor else None
        except Exception:
            exchanges[k] = None
    for sym in symbols:
        print('Processing', sym)
        try:
            bid, bsym = find_market(binance, sym)
            if not bsym:
                out[sym] = {'error': 'binance market not found'}; continue
            ob = binance.fetch_order_book(bsym, 100)
            asks = ob.get('asks', [])
            # simulate buy on binance
            cost_buy, filled_buy, lv_buy = simulate_from_orderbook(asks, 10000)
            avg_buy = cost_buy / filled_buy if filled_buy else None
            # funding
            cnt, total_f, avg_int = fetch_binance_funding(bsym)
            results = []
            for exid, exinst in exchanges.items():
                try:
                    if exinst is None:
                        results.append({'exchange': exid, 'error': 'adapter missing'})
                        continue
                    m_id, m_sym = find_market(exinst, sym)
                    if not m_sym:
                        results.append({'exchange': exid, 'error': 'market missing'}); continue
                    ob2 = exinst.fetch_order_book(m_sym, 100)
                    bids = ob2.get('bids', [])
                    cost_sell, filled_sell, lv_sell = simulate_from_orderbook(bids, 10000)
                    avg_sell = cost_sell / filled_sell if filled_sell else None
                    best_ask = float(asks[0][0]) if asks else 0.0
                    best_bid = float(bids[0][0]) if bids else 0.0
                    slippage_buy = (avg_buy - best_ask)/best_ask if best_ask else 0.0
                    slippage_sell = (best_bid - avg_sell)/best_bid if best_bid else 0.0
                    # funding income 6h
                    bin_hour = -avg_int if avg_int < 0 else avg_int
                    funding_income = bin_hour * 10000 * 6
                    fee = 4 * 0.0004 * 10000
                    slippage_cost = abs((avg_buy - best_ask)*filled_buy) + abs((best_bid - avg_sell)*filled_sell)
                    net = funding_income - fee - slippage_cost
                    results.append({'exchange': exid, 'avg_buy': avg_buy, 'avg_sell': avg_sell, 'slippage_buy': slippage_buy, 'slippage_sell': slippage_sell, 'est_6h_net': net})
                except Exception as e:
                    results.append({'exchange': exid, 'error': str(e)})
            out[sym] = {'binance_avg_buy': avg_buy, 'funding': {'count': cnt, 'total': total_f, 'avg_interval': avg_int}, 'candidates': sorted(results, key=lambda r: r.get('est_6h_net') or -1e9, reverse=True)}
        except Exception as e:
            out[sym] = {'error': str(e)}
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
