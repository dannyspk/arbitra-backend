#!/usr/bin/env python3
"""Check VIA network compatibility between MEXC and Gate.io"""
import os
import json
import hmac
import hashlib
import time
from urllib import request as _req
from urllib.parse import urlencode

print("=" * 80)
print("CHECKING VIA NETWORKS")
print("=" * 80)

# Check MEXC
print("\n1. MEXC VIA Networks:")
print("-" * 40)
api_key = os.environ.get('MEXC_API_KEY', '')
api_secret = os.environ.get('MEXC_API_SECRET', '')

if api_key and api_secret:
    timestamp = int(time.time() * 1000)
    params = {'timestamp': timestamp}
    query_string = urlencode(params)
    signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    
    url = f'https://api.mexc.com/api/v3/capital/config/getall?{query_string}&signature={signature}'
    req = _req.Request(url)
    req.add_header('X-MEXC-APIKEY', api_key)
    
    with _req.urlopen(req, timeout=10) as r:
        coins = json.load(r)
        via = None
        for coin in coins:
            if coin.get('coin', '') == 'VIA':
                via = coin
                break
        
        if via:
            print("Found VIA:")
            network_list = via.get('networkList', [])
            for net in network_list:
                network_name = net.get('network', '') or net.get('netWork', '')
                dep = net.get('depositEnable', False)
                wit = net.get('withdrawEnable', False)
                normalized = network_name.upper().replace('ETHEREUM', 'ERC20').replace('(', '').replace(')', '')
                print(f"  Network: {network_name}")
                print(f"    Normalized: {normalized}")
                print(f"    Deposit: {dep}, Withdraw: {wit}")
                print(f"    Both enabled: {dep and wit}")

# Check Gate.io
print("\n2. Gate.io VIA Networks:")
print("-" * 40)
with _req.urlopen('https://api.gateio.ws/api/v4/spot/currencies', timeout=10) as r:
    currencies = json.load(r)
    via = None
    for curr in currencies:
        if curr.get('currency', '').upper() == 'VIA':
            via = curr
            break
    
    if via:
        print("Found VIA:")
        print(f"  Currency: {via.get('currency')}")
        print(f"  Deposit disabled: {via.get('deposit_disabled')}")
        print(f"  Withdraw disabled: {via.get('withdraw_disabled')}")
        chain = via.get('chain', '')
        print(f"  Chain field: '{chain}'")
        
        if chain:
            chains = chain.split(',')
            for c in chains:
                c = c.strip().upper()
                normalized = c.replace('ETHEREUM', 'ERC20').replace('ETH', 'ERC20')
                print(f"    Chain: {c}")
                print(f"      Normalized: {normalized}")

# Compare
print("\n3. Comparison:")
print("-" * 40)
print("Network name standardization might be the issue.")
print("Common network names:")
print("  - BSC: Binance Smart Chain, BEP20, BSC, BINANCE-SMART-CHAIN")
print("  - Ethereum: ERC20, ETHEREUM, ETH")
print("  - Tron: TRC20, TRON, TRX")
print("  - Polygon: POLYGON, MATIC")
print("\nWe need to normalize these to match!")
