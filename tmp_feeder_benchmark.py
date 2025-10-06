"""Benchmark scanner time with and without feeders.

This script starts feeders (via tmp_start_all_feeders), runs a quick fast
probe/scan using tmp_compare_mexc_binance.quick_scan, and reports timings.
It performs both runs: one with feeders running and one without (stopped),
so you can compare wall-clock times.
"""
import time
import os
import sys

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from tmp_compare_mexc_binance import quick_scan, mock_mode, live_mode  # type: ignore
import statistics

def run_with_feeders_once(starter, feeders, symbols):
    # feeders should already be started/warmed by caller; run a single scan
    exs = live_mode(fast=True)
    if not exs:
        exs = mock_mode()
    t0 = time.perf_counter()
    res = quick_scan(exs, probe_symbols=symbols, min_profit_pct=0.01, collect_metrics=True)
    t1 = time.perf_counter()
    # res is (opps, metrics)
    opps, metrics = res
    return (t1 - t0), feeders, metrics

def run_without_feeders_once(starter, feeders, symbols):
    starter.stop_all(feeders)
    # ensure env flag is cleared for this process
    os.environ.pop('ARB_USE_WS_FEED', None)
    exs = live_mode(fast=True)
    if not exs:
        exs = mock_mode()
    t0 = time.perf_counter()
    res = quick_scan(exs, probe_symbols=symbols, min_profit_pct=0.01, collect_metrics=True)
    t1 = time.perf_counter()
    opps, metrics = res
    return (t1 - t0), metrics

def main():
    print('Starting feeders and benchmarking...')
    import tmp_start_all_feeders as starter
    symbols = ['BTC/USDT', 'ETH/USDT']
    iterations = 5
    with_times = []
    without_times = []
    with_metrics = []
    without_metrics = []
    # Start feeders once and run multiple iterations with them
    feeders = None
    try:
        feeders = starter.start_all(interval=1.0, symbols=symbols)
        try:
            time.sleep(5.0)  # warm-up
            for i in range(iterations):
                t, f, metrics = run_with_feeders_once(starter, feeders, symbols)
                with_times.append(t)
                with_metrics.append(metrics)
                print(f'  iteration {i+1} with feeders: {t:.3f}s metrics={metrics}')
        finally:
            # stop feeders before running without
            if feeders:
                starter.stop_all(feeders)
    except KeyboardInterrupt:
        print('\nBenchmark interrupted by user; stopping feeders...')
        if feeders:
            try:
                starter.stop_all(feeders)
            except Exception:
                pass
        return

    # Run iterations without feeders
    os.environ.pop('ARB_USE_WS_FEED', None)
    for i in range(iterations):
        t, metrics = run_without_feeders_once(starter, feeders, symbols)
        without_times.append(t)
        without_metrics.append(metrics)
        print(f'  iteration {i+1} without feeders: {t:.3f}s metrics={metrics}')

    print('\nSummary:')
    print(f'With feeders: median={statistics.median(with_times):.3f}s mean={statistics.mean(with_times):.3f}s std={statistics.pstdev(with_times):.3f}s')
    print(f'Without feeders: median={statistics.median(without_times):.3f}s mean={statistics.mean(without_times):.3f}s std={statistics.pstdev(without_times):.3f}s')
    # aggregate metrics
    def agg_metric(list_of_metrics, key):
        vals = [m.get(key, 0) for m in list_of_metrics]
        return sum(vals), statistics.median(vals) if vals else 0

    wf_sum, wf_med = agg_metric(with_metrics, 'feeder_hits')
    wft_sum, wft_med = agg_metric(with_metrics, 'fetch_ticker_calls')
    nwf_sum, nwf_med = agg_metric(without_metrics, 'feeder_hits')
    nwft_sum, nwft_med = agg_metric(without_metrics, 'fetch_ticker_calls')
    print(f'With feeders aggregated feeder_hits sum={wf_sum} median={wf_med}, fetch_ticker_calls sum={wft_sum} median={wft_med}')
    print(f'Without feeders aggregated feeder_hits sum={nwf_sum} median={nwf_med}, fetch_ticker_calls sum={nwft_sum} median={nwft_med}')

if __name__ == '__main__':
    main()
