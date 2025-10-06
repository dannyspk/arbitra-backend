#!/usr/bin/env python3
"""Simulate a market fill for a given notional on Binance USDT perpetual and compute 3-day P&L for an aggressive-hedge funding play.

Usage: python tools/simulate_fill_and_pnl.py [SYMBOL] [NOTIONAL]
Defaults: SYMBOL=MYXUSDT NOTIONAL=10000

Assumptions shown in output. Conservative and optimistic funding scenarios are reported.
"""
from __future__ import annotations
import sys, time, json, ssl, urllib.request, urllib.parse

API_DEPTH = 'https://fapi.binance.com/fapi/v1/depth'
API_FUND = 'https://fapi.binance.com/fapi/v1/fundingRate'

def fetch(url, params=None, timeout=20):
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, context=ctx, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf8'))

def simulate_market_buy(symbol, notional_usd, limit=100):
    depth = fetch(API_DEPTH, {'symbol': symbol, 'limit': limit})
    asks = depth.get('asks', [])
    if not asks:
        raise RuntimeError('no asks in depth')
    best_ask = float(asks[0][0])
    remaining = notional_usd
    cost = 0.0
    filled_qty = 0.0
    levels = 0
    for p_str, q_str in asks:
        p = float(p_str); q = float(q_str)
        level_notional = p * q
        if remaining <= 0:
            break
        take_notional = min(remaining, level_notional)
        take_qty = take_notional / p
        cost += take_qty * p
        filled_qty += take_qty
        remaining -= take_notional
        levels += 1
    executed_notional = cost
    avg_price = cost / filled_qty if filled_qty else 0.0
    slippage_pct = (avg_price - best_ask) / best_ask if best_ask else 0.0
    return {
        'symbol': symbol,
        'notional_requested': notional_usd,
        'executed_notional': executed_notional,
        'filled_qty': filled_qty,
        'avg_price': avg_price,
        'best_ask': best_ask,
        'levels_swept': levels,
        'slippage_pct': slippage_pct,
        'depth_sampled': len(asks)
    }

def fetch_funding_summary(symbol, start_ms, end_ms):
    recs = fetch(API_FUND, {'symbol': symbol, 'startTime': start_ms, 'endTime': end_ms, 'limit': 1000})
    total = 0.0; count = 0
    for r in recs:
        try:
            fr = float(r.get('fundingRate') or 0.0)
        except Exception:
            fr = 0.0
        total += fr; count += 1
    avg = total / count if count else 0.0
    return {'count': count, 'total': total, 'avg': avg}

def main(argv):
    symbol = (argv[1] if len(argv) > 1 else 'MYXUSDT').upper()
    notional = float(argv[2]) if len(argv) > 2 else 10000.0
    print(f"Simulating market buy {notional:.2f} USD on {symbol}")
    sim = simulate_market_buy(symbol, notional)
    print('Simulation result:')
    print(f"  best ask: {sim['best_ask']:.6f}")
    print(f"  avg executed price: {sim['avg_price']:.6f}")
    print(f"  executed notional: {sim['executed_notional']:.2f} (requested {sim['notional_requested']:.2f})")
    print(f"  filled qty: {sim['filled_qty']:.6f}")
    print(f"  levels swept: {sim['levels_swept']}")
    print(f"  slippage vs best ask: {sim['slippage_pct']*100:.4f}%")

    # fetch funding summary last 24h
    now_ms = int(time.time()*1000)
    start_ms = now_ms - 24*3600*1000
    fund = fetch_funding_summary(symbol, start_ms, now_ms)
    print(f"\nFunding summary (24h): intervals={fund['count']} cumulative={fund['total']:.8f} avg_interval={fund['avg']:.8f}")

    # compute PnL scenarios
    days = 3
    T = fund['total']
    count = fund['count']
    # optimistic: treat observed 24h total as daily funding (use abs because sign shows payers)
    daily_opt = abs(T)
    income_opt = daily_opt * notional * days
    # conservative: compute avg per observed interval, assume 3 funding intervals per day
    avg_interval = fund['avg']
    daily_cons = abs(avg_interval) * 3.0
    income_cons = daily_cons * notional * days

    # fees: assume taker fee 0.04% per trade, open+close both legs => 4 trades
    fee_rate = 0.0004
    fees_total = 4 * fee_rate * notional

    # slippage: take primary leg slippage cost and assume symmetric on hedge leg
    slippage_primary = (sim['avg_price'] - sim['best_ask']) * sim['filled_qty']
    slippage_total = abs(slippage_primary) * 2.0

    net_opt = income_opt - fees_total - slippage_total
    net_cons = income_cons - fees_total - slippage_total

    print('\nAssumptions: taker fee=0.04% (per trade), symmetric hedge slippage, hedge on another venue with similar liquidity.')
    print(f"Fees (4 taker trades): {fees_total:.2f}")
    print(f"Slippage cost (both legs): {slippage_total:.2f}")
    print('\n3-day P&L estimates:')
    print(f"  Optimistic (use observed 24h cumulative as daily): funding income={income_opt:.2f}, net={net_opt:.2f}")
    print(f"  Conservative (avg interval * 3 per day): funding income={income_cons:.2f}, net={net_cons:.2f}")

if __name__ == '__main__':
    main(sys.argv)
