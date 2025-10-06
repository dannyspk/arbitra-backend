#!/usr/bin/env python3
"""Test MEXC API for TRIBE deposit/withdrawal status"""
import os
import json
import hmac
import hashlib
import time
from urllib import request as _req
from urllib.parse import urlencode

api_key = os.environ.get('MEXC_API_KEY', '')
api_secret = os.environ.get('MEXC_API_SECRET', '')

if not api_key or not api_secret:
    print("❌ MEXC API credentials not found in environment")
    exit(1)

print(f"✓ API Key found (length: {len(api_key)})")
print(f"✓ API Secret found (length: {len(api_secret)})")
print()

try:
    # MEXC uses timestamp in milliseconds
    timestamp = int(time.time() * 1000)
    params = {'timestamp': timestamp}
    query_string = urlencode(params)
    signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    
    url = f'https://api.mexc.com/api/v3/capital/config/getall?{query_string}&signature={signature}'
    req = _req.Request(url)
    req.add_header('X-MEXC-APIKEY', api_key)
    
    print(f"Fetching: {url[:60]}...")
    with _req.urlopen(req, timeout=10) as r:
        coins = json.load(r)
        print(f"✓ Fetched {len(coins)} coins from MEXC")
        print()
        
        # Find TRIBE
        tribe = None
        for coin in coins:
            if coin.get('coin', '') == 'TRIBE':
                tribe = coin
                break
        
        if tribe:
            print("Found TRIBE:")
            print(json.dumps(tribe, indent=2))
            print()
            
            # Check status
            deposit = tribe.get('depositEnable', True) or tribe.get('depositAllEnable', True)
            withdraw = tribe.get('withdrawEnable', True) or tribe.get('withdrawAllEnable', True)
            
            print(f"Deposit enabled: {deposit}")
            print(f"Withdraw enabled: {withdraw}")
            
            # Check network info
            if 'networkList' in tribe:
                print(f"\nNetwork details:")
                for net in tribe['networkList']:
                    print(f"  {net.get('network', 'N/A')}: deposit={net.get('depositEnable', False)}, withdraw={net.get('withdrawEnable', False)}")
        else:
            print("❌ TRIBE not found in response")
            print("\nSample of available coins:")
            for coin in coins[:5]:
                print(f"  - {coin.get('coin', 'N/A')}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
