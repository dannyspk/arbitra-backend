import os
import runpy
os.environ['ARB_USE_CCXTPRO']='1'
runpy.run_path('tmp_compare_mexc_binance.py', run_name='__main__')
print('runner finished')
