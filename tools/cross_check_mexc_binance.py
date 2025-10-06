#!/usr/bin/env python3
"""Cross-check Binance vs MEXC for MYXUSDT: orderbook slippage + Binance funding -> 6-hour P&L.

Usage: python tools/cross_check_mexc_binance.py [SYMBOL] [NOTIONAL]
Defaults: SYMBOL=MYX/USDT NOTIONAL=10000
"""
from __future__ import annotations
import sys, time, json, urllib.request, urllib.parse, ssl
import ccxt

BINANCE_FUND_API = 'https://fapi.binance.com/fapi/v1/fundingRate'

def find_market(exchange, token):
    token = token.upper()
    markets = exchange.load_markets()
    # try direct symbol
    if token in markets:
        return markets[token]['id'], markets[token]['symbol']
    # find by contains
    for s, meta in markets.items():
        if token.replace('/', '') in s.replace('/', ''):
            return meta['id'], meta['symbol']
    return None, None

def simulate_market_side_from_orderbook(asks_or_bids, notional_usd, side='buy'):
    # asks_or_bids: list of [price, qty]
    remaining = notional_usd
    cost = 0.0
    filled_qty = 0.0
    levels = 0
    for p, q in asks_or_bids:
        p = float(p); q = float(q)
        lvl_not = p * q
        if remaining <= 0:
            break
        take_not = min(remaining, lvl_not)
        take_qty = take_not / p
        cost += take_qty * p
        filled_qty += take_qty
        remaining -= take_not
        levels += 1
    return {'executed_notional': cost, 'filled_qty': filled_qty, 'levels': levels}

def fetch_binance_funding(symbol, start_ms, end_ms):
    q = {'symbol': symbol.replace('/', ''), 'startTime': str(start_ms), 'endTime': str(end_ms), 'limit': '1000'}
    url = BINANCE_FUND_API + '?' + urllib.parse.urlencode(q)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode('utf8'))

def main(argv):
    token = argv[1] if len(argv) > 1 else 'MYX/USDT'
    notional = float(argv[2]) if len(argv) > 2 else 10000.0

    print('Loading exchanges (ccxt)')
    binance = ccxt.binance({'enableRateLimit': True})
    mexc = ccxt.mexc({'enableRateLimit': True})

    print('Finding markets...')
    bid, bsym = find_market(binance, token)
    mid, msym = find_market(mexc, token)
    if not bsym:
        print('Binance market not found for', token); return
    if not msym:
        print('MEXC market not found for', token); return
    print('Binance symbol:', bsym, 'MEXC symbol:', msym)

    print('Fetching orderbooks (limit 100)')
    b_ob = binance.fetch_order_book(bsym, limit=100)
    m_ob = mexc.fetch_order_book(msym, limit=100)

    # simulate buy on Binance (consume asks), sell on MEXC (consume bids)
    sim_buy = simulate_market_side_from_orderbook(b_ob['asks'], notional, 'buy')
    sim_sell = simulate_market_side_from_orderbook(m_ob['bids'], notional, 'sell')

    best_ask = float(b_ob['asks'][0][0]) if b_ob['asks'] else 0.0
    best_bid_m = float(m_ob['bids'][0][0]) if m_ob['bids'] else 0.0
    avg_buy = sim_buy['executed_notional'] / sim_buy['filled_qty'] if sim_buy['filled_qty'] else 0.0
    avg_sell = sim_sell['executed_notional'] / sim_sell['filled_qty'] if sim_sell['filled_qty'] else 0.0

    print('\nSimulation results:')
    print(f"  Binance best ask: {best_ask:.6f}, avg buy price: {avg_buy:.6f}, levels: {sim_buy['levels']}")
    print(f"  MEXC best bid: {best_bid_m:.6f}, avg sell price: {avg_sell:.6f}, levels: {sim_sell['levels']}")
    slippage_buy = (avg_buy - best_ask)/best_ask if best_ask else 0.0
    slippage_sell = (best_bid_m - avg_sell)/best_bid_m if best_bid_m else 0.0
    print(f"  slippage buy: {slippage_buy*100:.4f}%  slippage sell: {slippage_sell*100:.4f}%")

    # fetch binance funding last 24h
    now_ms = int(time.time()*1000)
    start_ms = now_ms - 24*3600*1000
    try:
        # bsym may include exchange suffix like 'MYX/USDT:USDT' — normalize to 'MYXUSDT'
        funding_symbol = bsym.split(':')[0].replace('/', '')
        funds = fetch_binance_funding(funding_symbol, start_ms, now_ms)
        total = sum(float(r.get('fundingRate') or 0.0) for r in funds)
        count = len(funds)
        avg_interval = total / count if count else 0.0
        print(f"\nBinance funding (24h): intervals={count} cumulative={total:.8f} avg_interval={avg_interval:.8f}")
    except Exception as e:
        print('Failed to fetch Binance funding:', e); total = 0.0; avg_interval = 0.0

    # assume MEXC funding approx 0 (per screenshot)
    mexc_hour = 0.0

    # compute 6-hour P&L
    hours = 6
    # funding per hour in decimal for longs (negative total -> longs earn)
    binance_hour = -avg_interval if avg_interval < 0 else avg_interval
    funding_income = binance_hour * notional * hours

    # fees
    fee_rate = 0.0004
    fees = 4 * fee_rate * notional
    # slippage costs: difference between executed notional and ideal at best prices
    slippage_cost_buy = (avg_buy - best_ask) * sim_buy['filled_qty']
    slippage_cost_sell = (best_bid_m - avg_sell) * sim_sell['filled_qty']
    slippage_total = abs(slippage_cost_buy) + abs(slippage_cost_sell)

    net = funding_income - fees - slippage_total

    print('\n6-hour estimate:')
    print(f"  funding_income (binance - mexc) ~ {funding_income:.2f}")
    print(f"  fees ~ {fees:.2f}")
    print(f"  slippage_total ~ {slippage_total:.2f}")
    print(f"  net_estimate ~ {net:.2f}")

if __name__ == '__main__':
    main(sys.argv)
