import os
os.environ['ARB_USE_CCXTPRO']='1'
import sys
import importlib
import os
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
	sys.path.insert(0, SRC)

m = importlib.import_module('arbitrage.exchanges')
print('CCXTExchange ->', m.CCXTExchange)
print('module ->', getattr(m.CCXTExchange, '__module__', None))
