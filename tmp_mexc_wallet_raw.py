"""Directly query MEXC public wallet endpoint and print XYM-related entries and a small sample.

Usage:
  python tmp_mexc_wallet_raw.py
"""
import requests
import pprint

url = 'https://www.mexc.com/api/v3/capital/config/getall'
print('GET', url)
try:
    r = requests.get(url, timeout=15.0, headers={'User-Agent': 'arbitrage-diagnostics/1.0'})
    print('HTTP', r.status_code)
    try:
        j = r.json()
    except Exception as e:
        print('Failed to parse JSON:', e)
        print(r.text[:2000])
        raise
    pp = pprint.PrettyPrinter(depth=2)
    if isinstance(j, dict) and 'data' in j and isinstance(j['data'], list):
        data = j['data']
        print('data length:', len(data))
        matches = [it for it in data if isinstance(it, dict) and ('XYM' in str(it.get('currency', '')).upper() or 'XYM' in str(it.get('coin', '')).upper() or 'XYM' in str(it.get('id', '')).upper())]
        print('matches:', len(matches))
        for m in matches[:10]:
            pp.pprint(m)
        if not matches:
            print('\nSample first 10 entries:')
            for it in data[:10]:
                pp.pprint({k: it.get(k) for k in ('currency','coin','name','withdrawAll','withdrawEnable','withdrawMin','chains') if k in it})
    else:
        print('Response JSON keys:', list(j.keys()) if isinstance(j, dict) else type(j))
        pp.pprint(j)
except Exception as e:
    print('Error calling endpoint:', e)
