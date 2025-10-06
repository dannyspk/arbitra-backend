#!/usr/bin/env python3
"""Fetch MYXUSDT klines from Binance USDT-M futures and write 15m and 1d CSVs to var/.
Writes:
  var/myx_15m.csv
  var/myx_1d.csv

These CSVs match the format expected by the backtest script: timestamp(ms),open,high,low,close,volume
"""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import csv
import os

API = 'https://fapi.binance.com/fapi/v1/klines'
SYMBOL = 'MYXUSDT'


def fetch(symbol, interval, limit=1500):
    q = {'symbol': symbol, 'interval': interval, 'limit': str(limit)}
    url = API + '?' + urlencode(q)
    req = Request(url, headers={'User-Agent': 'fetch-myx-klines/1.0'})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())


os.makedirs('var', exist_ok=True)
print('Fetching 15m...')
kl_15 = fetch(SYMBOL, '15m', limit=1500)
with open('var/myx_15m.csv', 'w', newline='', encoding='utf8') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp','open','high','low','close','volume'])
    for k in kl_15:
        writer.writerow([k[0], k[1], k[2], k[3], k[4], k[5]])
print('Wrote var/myx_15m.csv rows=', len(kl_15))

print('Fetching 1d...')
kl_1d = fetch(SYMBOL, '1d', limit=1500)
with open('var/myx_1d.csv', 'w', newline='', encoding='utf8') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp','open','high','low','close','volume'])
    for k in kl_1d:
        writer.writerow([k[0], k[1], k[2], k[3], k[4], k[5]])
print('Wrote var/myx_1d.csv rows=', len(kl_1d))
