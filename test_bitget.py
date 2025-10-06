#!/usr/bin/env python3
"""Test Bitget API integration"""
import json
from urllib import request as _req

try:
    print("Fetching Bitget tickers...")
    
    # Bitget requires User-Agent header
    req = _req.Request('https://api.bitget.com/api/v2/spot/market/tickers')
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Accept', 'application/json')
    
    with _req.urlopen(req, timeout=10) as r:
        data = json.load(r)
        tickers = data.get('data', [])
        print(f"✓ Fetched {len(tickers)} tickers")
        
        # Filter USDT pairs
        usdt_pairs = [t for t in tickers if t.get('symbol', '').endswith('USDT')]
        print(f"✓ Found {len(usdt_pairs)} USDT pairs")
        
        # Check volume filtering
        high_volume = []
        for t in usdt_pairs:
            try:
                symbol = t.get('symbol', '')
                price = float(t.get('lastPr', 0))
                volume = float(t.get('quoteVolume', 0))
                if price > 0 and volume > 10000:
                    high_volume.append({
                        'symbol': symbol,
                        'price': price,
                        'volume': volume
                    })
            except Exception as e:
                print(f"✗ Parse error for {symbol}: {e}")
        
        print(f"✓ {len(high_volume)} pairs with >$10k volume")
        print(f"\nSample high-volume pairs:")
        for pair in sorted(high_volume, key=lambda x: x['volume'], reverse=True)[:10]:
            print(f"  {pair['symbol']}: ${pair['price']:.4f} (vol: ${pair['volume']:,.0f})")
            
except Exception as e:
    print(f"✗ Error: {e}")
