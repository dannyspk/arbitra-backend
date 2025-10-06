"""Exchange adapters package."""

import os
from .base import Exchange

try:
	from .ccxt_adapter import CCXTExchange  # type: ignore
except Exception:
	CCXTExchange = None

# Optional ccxt.pro adapter (opt-in). If ARB_USE_CCXTPRO=1 is set we will
# prefer the CCXTProExchange implementation if available, otherwise fall back
# to the regular CCXTExchange.
try:
	if os.getenv('ARB_USE_CCXTPRO', '0') == '1':
		from .ccxt_pro_adapter import CCXTProExchange  # type: ignore
		CCXTExchange = CCXTProExchange  # type: ignore
except Exception:
	# keep CCXTExchange as previously imported (or None)
	pass

try:
	from .dex_adapter import DexAdapter  # type: ignore
except Exception:
	DexAdapter = None
try:
    from .mexc_adapter import MEXCExchange  # type: ignore
except Exception:
    MEXCExchange = None

__all__ = ["Exchange", "CCXTExchange", "DexAdapter", "MEXCExchange"]
