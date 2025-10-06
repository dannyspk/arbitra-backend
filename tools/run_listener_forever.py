#!/usr/bin/env python3
"""Run the Binance liquidation listener in a restart loop with logging and backoff.

Usage:
  python tools/run_listener_forever.py --stream '!forceOrder@arr' --duration 3600 --forward http://127.0.0.1:8000/liquidations/ingest

This script will append stdout/stderr from the listener to `tools/ccxt_out/binance_listener_supervisor.log`
and restart it with exponential backoff if it exits.
"""
import argparse
import subprocess
import sys
import time
import pathlib

LOG_PATH = pathlib.Path('tools/ccxt_out/binance_listener_supervisor.log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stream', default='!forceOrder@arr')
    p.add_argument('--duration', type=int, default=3600)
    p.add_argument('--forward', default=None)
    p.add_argument('--write', action='store_true', help='pass --write to the listener so it writes file, default false when forwarding')
    args = p.parse_args()

    backoff = 1.0
    max_backoff = 300.0
    attempt = 0

    while True:
        attempt += 1
        cmd = [sys.executable, 'tools/binance_liquidation_listener.py', '--stream', args.stream, '--duration', str(args.duration)]
        if args.forward:
            cmd += ['--forward', args.forward]
        if args.write:
            cmd += ['--write']

        start_ts = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        header = f"\n---- START {start_ts} attempt={attempt} cmd={' '.join(cmd)} ----\n"
        with LOG_PATH.open('a', encoding='utf-8') as fh:
            fh.write(header)
            fh.flush()
            try:
                print('Starting listener:', ' '.join(cmd))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            except Exception as e:
                err = f"Failed to start listener: {e}\n"
                print(err, end='')
                fh.write(err)
                fh.flush()
                sleep_for = min(backoff, max_backoff)
                print(f"Retrying in {sleep_for:.1f}s")
                time.sleep(sleep_for)
                backoff = min(backoff * 2.0, max_backoff)
                continue

            # stream process output into log file and to stdout
            try:
                for line in proc.stdout:
                    sys.stdout.write(line)
                    fh.write(line)
                    fh.flush()
            except Exception as e:
                fh.write(f"Error while reading process output: {e}\n")
            finally:
                proc.wait()
                exit_code = proc.returncode
                end_ts = time.strftime('%Y-%m-%dT%H:%M:%S%z')
                footer = f"---- EXIT {end_ts} code={exit_code} attempt={attempt} ----\n"
                fh.write(footer)
                fh.flush()
                print(footer)

        # if process exited with 0 and duration was the intended run (likely expected), we will still restart it
        sleep_for = min(backoff, max_backoff)
        print(f"Listener exited (code={exit_code}). Restarting in {sleep_for:.1f}s (attempt {attempt}). Log: {LOG_PATH}")
        time.sleep(sleep_for)
        backoff = min(backoff * 2.0, max_backoff)


if __name__ == '__main__':
    main()
