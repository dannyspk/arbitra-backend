import sys, os, time
sys.path.insert(0, os.path.abspath('src'))
from arbitrage.hotcoins import _binance_top_by_volume
from arbitrage.exchanges.gate_depth_feeder import GateDepthFeeder

def main():
    top = _binance_top_by_volume(top_n=5)
    if not top:
        print('no top symbols'); return
    syms = []
    for it in top:
        s = it.get('symbol')
        if not s: continue
        if '_' in s:
            g = s
        else:
            if s.endswith('USDT'):
                g = s[:-4] + '_' + s[-4:]
            else:
                g = s[:-3] + '_' + s[-3:]
        syms.append(g)
    print('subscribing to:', syms)
    feeder = GateDepthFeeder([g.replace('_','/') for g in syms])
    feeder.start()
    try:
        time.sleep(20)
        tk = feeder.get_tickers()
        print('\nRAW TICKERS:')
        for k,v in tk.items():
            print(k, v)
        print('\nRequested mapping:')
        for g in syms:
            key = g.replace('_','/')
            print(key, '->', tk.get(key))
    finally:
        feeder.stop()

if __name__ == '__main__':
    main()
