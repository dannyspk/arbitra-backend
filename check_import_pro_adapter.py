import sys,os
ROOT = os.path.abspath('.')
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
try:
    import arbitrage.exchanges.ccxt_pro_adapter as prot
    print('ccxt_pro_adapter imported OK ->', prot)
except Exception as e:
    print('ccxt_pro_adapter import failed:', e)
