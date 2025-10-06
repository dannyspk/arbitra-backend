"""Debug helper: Connect to Gate websocket, subscribe to a few symbols and print raw messages.

Run this from repo root: python tools/debug_gate_ws.py
"""
import asyncio
import json
import time
import os
import sys

sys.path.insert(0, os.path.abspath('src'))

import websockets


async def main():
    uri = 'wss://api.gateio.ws/ws/v4/'
    symbols = ['BTC_USDT', 'ETH_USDT']
    req = lambda ch: json.dumps({'time': int(time.time()), 'channel': ch, 'event': 'subscribe', 'payload': symbols})
    try:
        async with websockets.connect(uri, max_size=None) as ws:
            print('connected, sending subs')
            await ws.send(req('spot.tickers'))
            await ws.send(req('spot.book_ticker'))
            t0 = time.time()
            while time.time() - t0 < 10:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                print('RAW:', msg)
    except Exception as e:
        print('error', e)


if __name__ == '__main__':
    asyncio.run(main())
