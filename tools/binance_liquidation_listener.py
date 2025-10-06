"""Binance USDS-m futures liquidation listener.

Usage:
  python tools/binance_liquidation_listener.py --stream '!forceOrder@arr' --duration 15

Writes JSON lines to tools/ccxt_out/binance_force_orders_ws.log and prints summaries to stdout.
"""
import asyncio
import json
import argparse
import pathlib
from datetime import datetime, timezone

try:
    import websockets
except Exception:
    websockets = None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def listen(stream: str, out_path: pathlib.Path, duration: int):
    if websockets is None:
        raise ImportError('websockets package not installed; run: python -m pip install websockets')
    url = f"wss://fstream.binance.com/stream?streams={stream}"
    end_time = asyncio.get_event_loop().time() + duration

    # reconnect loop with exponential backoff
    backoff = 1.0
    max_backoff = 60.0
    while True:
        time_left = end_time - asyncio.get_event_loop().time()
        if time_left <= 0:
            # duration expired
            break
        try:
            async with websockets.connect(url, max_size=None) as ws:
                print(now_iso(), 'connected to', url)
                # reset backoff after successful connect
                backoff = 1.0
                while True:
                    time_left = end_time - asyncio.get_event_loop().time()
                    if time_left <= 0:
                        # requested duration expired
                        break
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=time_left)
                    except asyncio.TimeoutError:
                        # reached requested duration
                        break
                    except Exception as e:
                        print(now_iso(), 'recv error:', repr(e))
                        # break to reconnect
                        break
                    # process message payload
                    try:
                        data = json.loads(msg)
                    except Exception:
                        # write raw
                        entry = {'ts': now_iso(), 'raw': msg}
                        try:
                            if getattr(listen, '_write_file', True):
                                with out_path.open('a', encoding='utf-8') as fh:
                                    fh.write(json.dumps(entry) + '\n')
                        except Exception:
                            pass
                        print(now_iso(), 'raw msg written')
                        continue
                    payload = data.get('data') or data
                    records = payload if isinstance(payload, list) else [payload]
                    # append to log (optional) and optionally forward
                    try:
                        entry_list = [{'ts': now_iso(), 'msg': rec} for rec in records]
                        if getattr(listen, '_write_file', True):
                            try:
                                with out_path.open('a', encoding='utf-8') as fh:
                                    for entry in entry_list:
                                        fh.write(json.dumps(entry) + '\n')
                            except Exception as e:
                                print(now_iso(), 'file write error:', repr(e))
                        # forward if configured
                        if hasattr(listen, '_forward_url') and listen._forward_url:
                            for entry in entry_list:
                                try:
                                    import requests
                                    requests.post(listen._forward_url, json=entry, timeout=1.0)
                                except Exception as e:
                                    print(now_iso(), 'forward error:', repr(e))
                    except Exception as e:
                        print(now_iso(), 'process entry error:', repr(e))
                    # print concise summary lines
                    for rec in records:
                        try:
                            sym = rec.get('symbol') or rec.get('s') or rec.get('S') or 'unknown'
                            price = rec.get('price') or rec.get('p') or rec.get('P')
                            qty = rec.get('qty') or rec.get('q') or rec.get('Q')
                            side = rec.get('side') or rec.get('S') or rec.get('s')
                            print(now_iso(), sym, 'price=', price, 'qty=', qty, 'side=', side)
                        except Exception:
                            continue
        except Exception as e:
            print(now_iso(), 'connection error:', repr(e))
        # reconnect/backoff handling
        time_left = end_time - asyncio.get_event_loop().time()
        if time_left <= 0:
            break
        sleep_for = min(backoff, time_left)
        print(now_iso(), 'reconnecting in', f"{sleep_for:.1f}s", 'backoff=', f"{backoff:.1f}s")
        await asyncio.sleep(sleep_for)
        backoff = min(backoff * 2.0, max_backoff)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stream', default='!forceOrder@arr', help='stream to subscribe (default all-market force orders)')
    p.add_argument('--duration', type=int, default=30, help='seconds to run before exiting')
    p.add_argument('--out', default='tools/ccxt_out/binance_force_orders_ws.log')
    p.add_argument('--forward', default=None, help='HTTP endpoint to forward events to (e.g. http://127.0.0.1:8000/liquidations/ingest)')
    p.add_argument('--write', dest='write', action='store_true', help='When --forward is used, also write to file if --write is passed')
    args = p.parse_args()

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # attach forward url and write behavior to function for access in listener
        if args.forward:
            listen._forward_url = args.forward
            listen._write_file = bool(args.write)
        else:
            listen._forward_url = None
            listen._write_file = True
        asyncio.run(listen(args.stream, out_path, args.duration))
    except KeyboardInterrupt:
        print(now_iso(), 'stopped by user')
    except Exception as e:
        print(now_iso(), 'fatal', e)


if __name__ == '__main__':
    main()
