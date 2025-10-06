#!/usr/bin/env python3
import os
import json
import time

# Ensure package import path
# run with PYTHONPATH=src

from arbitrage.opportunities import compute_dryrun_opportunities
from arbitrage.exchanges.mock_exchange import MockExchange

# Try to import MEXCExchange adapter (which uses ccxt). If unavailable, fall back to mock
try:
    from arbitrage.exchanges.mexc_adapter import MEXCExchange
    has_mexc = True
except Exception as e:
    MEXCExchange = None
    has_mexc = False

exchanges = []
# include a mock exchange to ensure some opportunities exist
exchanges.append(MockExchange('CEX-A', {'BTC/USDT': 50000.0, 'ETH/USDT': 3000.0}))

if has_mexc:
    try:
        # instantiate MEXCExchange (may use ccxt)
        mex = MEXCExchange()
        exchanges.append(mex)
    except Exception as e:
        # fallback to mock mexc provider
        exchanges.append(MockExchange('mexc', {'BTC/USDT': 50100.0, 'ETH/USDT': 2990.0}))
else:
    exchanges.append(MockExchange('mexc', {'BTC/USDT': 50100.0, 'ETH/USDT': 2990.0}))

# run the compute_dryrun_opportunities function
try:
    out = compute_dryrun_opportunities(exchanges, amount=1.0, min_profit_pct=0.0)
    sample = out[:10]
    print(json.dumps({'sample_count': len(sample), 'sample': sample}, indent=2))
except Exception as e:
    print(json.dumps({'error': str(e)}))
    raise
