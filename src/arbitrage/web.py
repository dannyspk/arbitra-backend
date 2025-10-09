from __future__ import annotations
import asyncio
import json
import os
import subprocess
from typing import Dict, Optional
import time

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from urllib import request as _urllib_request, parse as _urllib_parse, error as _urllib_error
import datetime as _dt
from fastapi.middleware.cors import CORSMiddleware

# Project root (two levels up from this module when running from source),
# fallback to cwd.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if not os.path.isdir(ROOT):
    ROOT = os.getcwd()

from .executor import Executor
from .scanner import Opportunity
from .exchanges.mock_exchange import MockExchange
from .opportunities import compute_dryrun_opportunities
from .hotcoins import find_hot_coins
from .feeder_utils import start_all as feeders_start_all, stop_all as feeders_stop_all

# Import social sentiment router
try:
    from .api.social_sentiment import router as social_sentiment_router
    SOCIAL_SENTIMENT_AVAILABLE = True
except ImportError:
    SOCIAL_SENTIMENT_AVAILABLE = False

# -----------------------------------------------------------------------------
# Deposit/Withdrawal Status Cache
# -----------------------------------------------------------------------------
# Cache structure: {exchange: {asset: {'deposit': bool, 'withdraw': bool, 'networks': set, 'timestamp': float}}}
_deposit_withdraw_cache = {}
_cache_ttl_seconds = 3600  # 1 hour cache

def _normalize_network_name(network: str) -> str:
    """Normalize network names to a common format for matching across exchanges"""
    if not network:
        return ''
    
    # Convert to uppercase and remove common noise
    normalized = network.upper().strip()
    normalized = normalized.replace('(', '').replace(')', '').replace('-', '').replace('_', '').replace(' ', '')
    
    # Map common network name variants to standard names
    # BSC / BEP20 / Binance Smart Chain
    if 'BSC' in normalized or 'BEP20' in normalized or 'BINANCESMARTCHAIN' in normalized or 'BNBSMARTCHAIN' in normalized or 'BNB' in normalized:
        return 'BSC'
    
    # Ethereum / ERC20
    if 'ERC20' in normalized or 'ETHEREUM' in normalized or normalized == 'ETH':
        return 'ERC20'
    
    # Tron / TRC20
    if 'TRC20' in normalized or 'TRON' in normalized or normalized == 'TRX':
        return 'TRC20'
    
    # Polygon / MATIC
    if 'POLYGON' in normalized or normalized == 'MATIC':
        return 'POLYGON'
    
    # Arbitrum
    if 'ARBITRUM' in normalized or normalized == 'ARB' or 'ARBONE' in normalized:
        return 'ARBITRUM'
    
    # Optimism
    if 'OPTIMISM' in normalized or normalized == 'OP':
        return 'OPTIMISM'
    
    # Avalanche
    if 'AVALANCHE' in normalized or 'AVAX' in normalized or normalized == 'CCHAIN':
        return 'AVALANCHE'
    
    # Solana
    if 'SOLANA' in normalized or normalized == 'SOL':
        return 'SOLANA'
    
    # If no match, return the cleaned-up version
    return normalized

def _get_cached_status(exchange: str, asset: str):
    """Get cached deposit/withdrawal status if available and not expired"""
    if exchange not in _deposit_withdraw_cache:
        return None
    if asset not in _deposit_withdraw_cache[exchange]:
        return None
    
    cached = _deposit_withdraw_cache[exchange][asset]
    if time.time() - cached.get('timestamp', 0) > _cache_ttl_seconds:
        return None  # Expired
    
    return {
        'deposit_enabled': cached.get('deposit', True),
        'withdraw_enabled': cached.get('withdraw', True),
        'networks': cached.get('networks', set())
    }

def _set_cached_status(exchange: str, asset: str, deposit: bool, withdraw: bool, networks: set = None):
    """Cache deposit/withdrawal status with available networks"""
    if exchange not in _deposit_withdraw_cache:
        _deposit_withdraw_cache[exchange] = {}
    
    _deposit_withdraw_cache[exchange][asset] = {
        'deposit': deposit,
        'withdraw': withdraw,
        'networks': networks if networks is not None else set(),
        'timestamp': time.time()
    }

def _check_common_networks(buy_exchange: str, sell_exchange: str, asset: str):
    """Check if two exchanges have at least one common network for transfers"""
    buy_status = _get_cached_status(buy_exchange, asset)
    sell_status = _get_cached_status(sell_exchange, asset)
    
    if not buy_status or not sell_status:
        return True  # If we don't have network info, assume compatible
    
    buy_networks = buy_status.get('networks', set())
    sell_networks = sell_status.get('networks', set())
    
    if not buy_networks or not sell_networks:
        return True  # If network info not available, assume compatible
    
    # Check for common networks
    common = buy_networks & sell_networks
    return len(common) > 0

# -----------------------------------------------------------------------------
# Connection manager
# -----------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.add(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active.remove(websocket)
        except KeyError:
            pass

    async def broadcast(self, message: str):
        """Broadcast message to all connected websockets concurrently."""
        dead: list[WebSocket] = []

        async def _send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=1.0)
            except Exception:
                dead.append(ws)

        await asyncio.gather(*[_send(ws) for ws in list(self.active)], return_exceptions=True)
        for ws in dead:
            self.disconnect(ws)


app = FastAPI()

# Include social sentiment router if available
if SOCIAL_SENTIMENT_AVAILABLE:
    app.include_router(social_sentiment_router)

# Endpoint: serve the latest hotcoins 1h analysis JSON if present
@app.get('/api/hotcoins/1h-analysis')
def get_hotcoins_1h_analysis():
    path = os.path.join(ROOT, 'var', 'hotcoins_1h_analysis.json')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='analysis-not-found')
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data
    except Exception:
        raise HTTPException(status_code=500, detail='failed-to-read-analysis')


@app.get('/api/hotcoins/4h-analysis')
def get_hotcoins_4h_analysis():
    path = os.path.join(ROOT, 'var', 'hotcoins_4h_analysis.json')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='analysis-not-found')
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data
    except Exception:
        raise HTTPException(status_code=500, detail='failed-to-read-analysis')


@app.get('/api/hotcoins/combined-analysis')
def get_hotcoins_combined_analysis():
    path = os.path.join(ROOT, 'var', 'hotcoins_combined_analysis.json')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='analysis-not-found')
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data
    except Exception:
        raise HTTPException(status_code=500, detail='failed-to-read-analysis')


@app.get('/api/ai-analysis/{symbol}')
def get_ai_analysis(symbol: str):
    """
    Compute real-time AI analysis for a specific symbol.
    Fetches 1h and 4h klines from Binance and computes technical indicators + trend prediction.
    """
    import statistics
    from urllib import request as _req, parse as _parse
    
    symbol_upper = symbol.upper()
    
    def fetch_klines(sym: str, interval: str = '1m', limit: int = 60):
        """Fetch klines from Binance Futures API"""
        try:
            q = _parse.urlencode({'symbol': sym, 'interval': interval, 'limit': str(limit)})
            # Use Binance Futures API for USDT perpetual contracts
            url = f"https://fapi.binance.com/fapi/v1/klines?{q}"
            with _req.urlopen(url, timeout=10) as r:
                return json.load(r)
        except Exception as e:
            print(f"Error fetching klines for {sym}: {e}")
            return None
    
    def analyze_klines(klines):
        """Analyze klines and compute indicators"""
        if not klines or len(klines) < 2:
            return None
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        n = len(closes)
        
        last = closes[-1]
        first = closes[0]
        pct_change = (last / first - 1.0) * 100.0
        
        # Linear regression slope
        xs = list(range(n))
        xmean = (n-1)/2.0
        ymean = statistics.mean(closes)
        num = sum((x - xmean)*(y - ymean) for x,y in zip(xs, closes))
        den = sum((x - xmean)**2 for x in xs)
        slope = num/den if den != 0 else 0.0
        
        # SMAs
        sma30 = statistics.mean(closes[-30:]) if n >= 30 else statistics.mean(closes)
        sma50 = statistics.mean(closes[-50:]) if n >= 50 else statistics.mean(closes)
        
        # RSI (14 period)
        rsi = None
        if n >= 15:
            gains = []
            losses = []
            for i in range(1, min(15, n)):
                diff = closes[-i] - closes[-i-1]
                if diff > 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(diff))
            avg_gain = statistics.mean(gains) if gains else 0
            avg_loss = statistics.mean(losses) if losses else 0
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100 if avg_gain > 0 else 50
        
        # Volatility (standard deviation of returns)
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, n)]
        volatility = statistics.stdev(returns) if len(returns) > 1 else 0
        
        # Support/Resistance levels
        recent_high = max(highs[-20:]) if n >= 20 else max(highs)
        recent_low = min(lows[-20:]) if n >= 20 else min(lows)
        
        # Quote volume
        quote_vol = 0.0
        try:
            for k in klines:
                qv = k[7] if len(k) > 7 else None
                if qv is not None:
                    quote_vol += float(qv)
        except Exception:
            pass
        
        return {
            'first': first,
            'last': last,
            'pct_change': pct_change,
            'slope': slope,
            'sma30': sma30,
            'sma50': sma50,
            'rsi': rsi,
            'volatility': volatility * 100,  # as percentage
            'recent_high': recent_high,
            'recent_low': recent_low,
            'quote_volume': quote_vol,
        }
    
    def classify_trend(analysis, min_quote_vol=1000.0):
        """Classify trend and confidence based on indicators"""
        if not analysis:
            return 'Unknown', 0
        
        pct = analysis['pct_change']
        slope = analysis['slope']
        rsi = analysis.get('rsi', 50)
        above_sma30 = analysis['last'] - analysis['sma30']
        qv = analysis.get('quote_volume', 0.0)
        
        # Confidence factors (0-1 scale for each)
        confidence_factors = []
        
        # Low volume reduces confidence significantly
        vol_conf = min(1.0, qv / min_quote_vol) if qv > 0 else 0
        confidence_factors.append(vol_conf * 0.3)  # 30% weight on volume
        
        # Price change magnitude
        price_conf = min(1.0, abs(pct) / 2.0)  # 2% change = full confidence
        confidence_factors.append(price_conf * 0.25)  # 25% weight
        
        # Slope agreement with price change
        if (pct > 0 and slope > 0) or (pct < 0 and slope < 0):
            confidence_factors.append(0.2)  # 20% weight
        
        # SMA position agreement
        if (pct > 0 and above_sma30 > 0) or (pct < 0 and above_sma30 < 0):
            confidence_factors.append(0.15)  # 15% weight
        
        # RSI confirmation
        if rsi is not None:
            if pct > 0 and rsi > 50:
                confidence_factors.append(0.1)  # 10% weight
            elif pct < 0 and rsi < 50:
                confidence_factors.append(0.1)
        
        total_confidence = sum(confidence_factors)
        
        # Determine trend
        if qv < min_quote_vol:
            trend = 'Neutral (Low Volume)'
        elif pct >= 0.8 and above_sma30 > 0 and slope > 0:
            trend = 'Strong Bullish'
        elif pct <= -0.8 and above_sma30 < 0 and slope < 0:
            trend = 'Strong Bearish'
        elif pct >= 0.3 and (above_sma30 > 0 or slope > 0):
            trend = 'Bullish'
        elif pct <= -0.3 and (above_sma30 < 0 or slope < 0):
            trend = 'Bearish'
        elif pct > 0.1:
            trend = 'Mild Bullish'
        elif pct < -0.1:
            trend = 'Mild Bearish'
        else:
            trend = 'Neutral'
        
        # Convert to percentage (0-100)
        confidence_pct = int(total_confidence * 100)
        
        return trend, confidence_pct
    
    try:
        # Fetch 1h data (60 x 1m candles)
        klines_1h = fetch_klines(symbol_upper, '1m', 60)
        analysis_1h = analyze_klines(klines_1h) if klines_1h else None
        trend_1h, conf_1h = classify_trend(analysis_1h, min_quote_vol=1000.0) if analysis_1h else ('Unknown', 0)
        
        # Fetch 4h data (240 x 1m candles)
        klines_4h = fetch_klines(symbol_upper, '1m', 240)
        analysis_4h = analyze_klines(klines_4h) if klines_4h else None
        trend_4h, conf_4h = classify_trend(analysis_4h, min_quote_vol=4000.0) if analysis_4h else ('Unknown', 0)
        
        # Combined confidence (weighted average favoring longer timeframe)
        combined_confidence = int((conf_1h * 0.4 + conf_4h * 0.6))
        
        # Overall trend (4h has more weight)
        overall_trend = trend_4h if conf_4h >= conf_1h else trend_1h
        
        return {
            'symbol': symbol_upper,
            'timestamp': time.time(),
            '1h': {
                'trend': trend_1h,
                'confidence': conf_1h,
                'analysis': analysis_1h
            },
            '4h': {
                'trend': trend_4h,
                'confidence': conf_4h,
                'analysis': analysis_4h
            },
            'overall': {
                'trend': overall_trend,
                'confidence': combined_confidence
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


@app.get('/api/opportunities')
def get_opportunities_snapshot():
    """Return the latest opportunities snapshot produced by the background scanner.

    This mirrors what the UI receives over the /ws/opportunities websocket and
    allows external tools to fetch the same pair list the front-end displays.
    """
    global latest_opportunities
    if latest_opportunities is None:
        return {'opportunities': []}
    return latest_opportunities


@app.get('/api/hotcoins')
def get_hotcoins_snapshot():
    """Return current hotcoins list. This mirrors what the /ws/hotcoins websocket
    broadcasts and prefers feeder snapshots when available so external tools can
    fetch the exact list the frontend displays.
    """
    try:
        # Build feeder list the same way the hotcoins loop does
        try:
            from .exchanges.ws_feed_manager import get_feeder
        except Exception:
            get_feeder = None

        raw = os.environ.get('ARB_HOT_EXCHANGES', 'binance,coinbase,mexc')
        exch_ids = [e.strip() for e in raw.split(',') if e.strip()]
        exchanges_list = []
        for eid in exch_ids:
            feeder = None
            try:
                if get_feeder is not None:
                    feeder = get_feeder(eid)
            except Exception:
                feeder = None
            if feeder is not None and hasattr(feeder, 'get_tickers'):
                exchanges_list.append(feeder)

        # If we have feeders, pass them to find_hot_coins to get the enriched,
        # feeder-backed hot list. If none, find_hot_coins will use Binance REST.
        hot = find_hot_coins(exchanges_list if exchanges_list else None)
        return {'hotcoins': hot}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'failed-to-get-hotcoins: {e}')


@app.get('/api/debug/status-cache')
def debug_status_cache(exchange: str = None, symbol: str = None):
    """Debug endpoint to check deposit/withdrawal status cache"""
    import time
    
    if exchange and symbol:
        # Check specific exchange and symbol
        key = f"{exchange}:{symbol}"
        if key in _deposit_withdraw_cache:
            cached = _deposit_withdraw_cache[key]
            age = time.time() - cached['timestamp']
            return {
                'exchange': exchange,
                'symbol': symbol,
                'deposit_enabled': cached['deposit'],
                'withdraw_enabled': cached['withdraw'],
                'cache_age_seconds': int(age),
                'cache_expires_in': int(3600 - age)
            }
        else:
            return {'error': f'No cache entry for {key}'}
    elif exchange:
        # Show all symbols for an exchange
        entries = {}
        for key, val in _deposit_withdraw_cache.items():
            if key.startswith(f"{exchange}:"):
                symbol_name = key.split(':', 1)[1]
                age = time.time() - val['timestamp']
                entries[symbol_name] = {
                    'deposit': val['deposit'],
                    'withdraw': val['withdraw'],
                    'age_seconds': int(age)
                }
        return {'exchange': exchange, 'cached_symbols': len(entries), 'entries': entries}
    else:
        # Show summary of all exchanges
        summary = {}
        for key in _deposit_withdraw_cache.keys():
            exch = key.split(':', 1)[0]
            summary[exch] = summary.get(exch, 0) + 1
        return {'total_entries': len(_deposit_withdraw_cache), 'by_exchange': summary}


@app.get('/api/spot-arbitrage')
def get_spot_arbitrage_opportunities():
    """Scan spot markets across Binance, MEXC, Gate.io, KuCoin, and Bitget for arbitrage opportunities.
    
    Returns pairs with price differences that have decent liquidity and volume.
    """
    from urllib import request as _req
    import statistics
    
    def fetch_binance_trading_symbols():
        """Fetch list of actively trading symbols on Binance (status=TRADING)"""
        try:
            with _req.urlopen('https://api.binance.com/api/v3/exchangeInfo', timeout=10) as r:
                data = json.load(r)
                trading_symbols = set()
                for symbol_info in data.get('symbols', []):
                    if symbol_info.get('status') == 'TRADING':
                        trading_symbols.add(symbol_info.get('symbol'))
                print(f"Found {len(trading_symbols)} actively trading symbols on Binance")
                return trading_symbols
        except Exception as e:
            print(f"Failed to fetch Binance exchange info: {e}")
            return set()
    
    def fetch_binance_spot_tickers():
        try:
            with _req.urlopen('https://api.binance.com/api/v3/ticker/24hr', timeout=10) as r:
                return json.load(r)
        except Exception as e:
            print(f"Failed to fetch Binance tickers: {e}")
            return []
    
    def fetch_mexc_spot_tickers():
        try:
            with _req.urlopen('https://api.mexc.com/api/v3/ticker/24hr', timeout=10) as r:
                return json.load(r)
        except Exception as e:
            print(f"Failed to fetch MEXC tickers: {e}")
            return []
    
    def fetch_gateio_spot_tickers():
        try:
            with _req.urlopen('https://api.gateio.ws/api/v4/spot/tickers', timeout=10) as r:
                return json.load(r)
        except Exception as e:
            print(f"Failed to fetch Gate.io tickers: {e}")
            return []
    
    def fetch_kucoin_spot_tickers():
        try:
            with _req.urlopen('https://api.kucoin.com/api/v1/market/allTickers', timeout=10) as r:
                data = json.load(r)
                return data.get('data', {}).get('ticker', [])
        except Exception as e:
            print(f"Failed to fetch KuCoin tickers: {e}")
            return []
    
    def fetch_bitget_spot_tickers():
        try:
            # Bitget requires User-Agent header
            req = _req.Request('https://api.bitget.com/api/v2/spot/market/tickers')
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', 'application/json')
            
            with _req.urlopen(req, timeout=10) as r:
                data = json.load(r)
                tickers = data.get('data', [])
                print(f"Fetched {len(tickers)} Bitget tickers")
                return tickers
        except Exception as e:
            print(f"Failed to fetch Bitget tickers: {e}")
            return []
    
    def fetch_kucoin_trading_symbols():
        """Fetch list of actively trading symbols on KuCoin (enableTrading=true)"""
        try:
            with _req.urlopen('https://api.kucoin.com/api/v1/symbols', timeout=10) as r:
                data = json.load(r)
                trading_symbols = set()
                for symbol_info in data.get('data', []):
                    if symbol_info.get('enableTrading', False):
                        # KuCoin uses hyphenated symbols like BTC-USDT, convert to BTCUSDT
                        symbol = symbol_info.get('symbol', '').replace('-', '')
                        trading_symbols.add(symbol)
                print(f"Found {len(trading_symbols)} actively trading symbols on KuCoin")
                return trading_symbols
        except Exception as e:
            print(f"Failed to fetch KuCoin symbols: {e}")
            return set()
    
    def calculate_arbitrage_pnl(symbol, buy_price, sell_price, buy_exchange, sell_exchange, notional=100):
        """Calculate realistic PnL for arbitrage considering fees and slippage
        
        Args:
            symbol: Trading pair symbol
            buy_price: Price on buy exchange
            sell_price: Price on sell exchange
            buy_exchange: Exchange to buy from
            sell_exchange: Exchange to sell to
            notional: Trade size in USDT (default $100)
        
        Returns:
            dict with breakdown of costs and final PnL
        """
        base_asset = symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')
        
        # Trading fees (spot maker/taker average)
        trading_fees = {
            'Binance': 0.001,   # 0.1%
            'MEXC': 0.002,      # 0.2%
            'Gate.io': 0.002,   # 0.2%
            'KuCoin': 0.001,    # 0.1%
            'Bitget': 0.001     # 0.1%
        }
        
        # Typical withdrawal fees in USDT value (estimated averages)
        # These vary by network but using common mainnet fees
        withdrawal_fees_usd = {
            'Binance': 1.0,     # Usually $0.5-2 depending on coin
            'MEXC': 2.0,        # Usually $1-3
            'Gate.io': 1.5,     # Usually $0.8-2.5
            'KuCoin': 1.5,      # Usually $1-2.5
            'Bitget': 1.5       # Usually $1-2
        }
        
        # Calculate quantities
        buy_fee_rate = trading_fees.get(buy_exchange, 0.002)
        sell_fee_rate = trading_fees.get(sell_exchange, 0.002)
        withdrawal_fee_usd = withdrawal_fees_usd.get(buy_exchange, 2.0)
        
        # Buy side: notional / price = quantity, minus trading fee
        quantity = (notional / buy_price) * (1 - buy_fee_rate)
        buy_cost = notional  # Total cost including fee
        
        # Sell side: quantity * price, minus trading fee
        sell_proceeds = quantity * sell_price * (1 - sell_fee_rate)
        
        # Withdrawal fee in quantity terms
        withdrawal_fee_quantity = withdrawal_fee_usd / buy_price
        quantity_after_withdrawal = quantity - withdrawal_fee_quantity
        
        # Recalculate sell proceeds after withdrawal fee
        sell_proceeds_after_fees = quantity_after_withdrawal * sell_price * (1 - sell_fee_rate)
        
        # Slippage estimate (0.1% for liquid pairs, 0.5% for thin orderbooks)
        # Use volume as proxy for liquidity
        slippage_rate = 0.001  # Default 0.1%
        slippage_cost = sell_proceeds_after_fees * slippage_rate
        
        # Final PnL
        gross_profit = sell_proceeds_after_fees - buy_cost
        net_profit = gross_profit - slippage_cost
        roi = (net_profit / notional) * 100
        
        return {
            'notional_usd': notional,
            'quantity': quantity,
            'buy_cost_usd': buy_cost,
            'sell_proceeds_usd': sell_proceeds_after_fees,
            'trading_fees_usd': (notional * buy_fee_rate) + (sell_proceeds_after_fees * sell_fee_rate),
            'withdrawal_fee_usd': withdrawal_fee_usd,
            'slippage_cost_usd': slippage_cost,
            'gross_profit_usd': gross_profit,
            'net_profit_usd': net_profit,
            'roi_percent': roi,
            'is_profitable': net_profit > 0
        }
    
    def batch_fetch_kucoin_currencies():
        """Fetch all currency status from KuCoin in one call and cache"""
        try:
            with _req.urlopen('https://api.kucoin.com/api/v1/currencies', timeout=10) as r:
                data = json.load(r)
                if data.get('code') == '200000':
                    currencies = data.get('data', [])
                    for curr in currencies:
                        asset = curr.get('currency', '')
                        if asset:
                            deposit = curr.get('isDepositEnabled', True)
                            withdraw = curr.get('isWithdrawEnabled', True)
                            
                            # Extract available networks (KuCoin uses 'chains' array)
                            available_networks = set()
                            chains = curr.get('chains', [])
                            for chain in chains:
                                if chain.get('isDepositEnabled', False) and chain.get('isWithdrawEnabled', False):
                                    chain_name = chain.get('chainName', '') or chain.get('chain', '')
                                    if chain_name:
                                        # Normalize network names
                                        normalized = _normalize_network_name(chain_name)
                                        if normalized:
                                            available_networks.add(normalized)
                            
                            _set_cached_status('KuCoin', asset, deposit, withdraw, available_networks)
                    print(f"Cached {len(currencies)} KuCoin currency statuses")
        except Exception as e:
            print(f"Failed to batch fetch KuCoin currencies: {e}")
    
    def batch_fetch_gateio_currencies():
        """Fetch all currency status from Gate.io spot currencies endpoint and cache"""
        try:
            with _req.urlopen('https://api.gateio.ws/api/v4/spot/currencies', timeout=10) as r:
                currencies = json.load(r)
                for curr in currencies:
                    currency = curr.get('currency', '').upper()
                    if not currency:
                        continue
                    
                    # Check deposit/withdraw status from the currency object
                    deposit_disabled = curr.get('deposit_disabled', False)
                    withdraw_disabled = curr.get('withdraw_disabled', False)
                    
                    # Extract available networks (Gate.io uses 'chain' field)
                    available_networks = set()
                    chains = curr.get('chain', '').split(',') if curr.get('chain') else []
                    for chain in chains:
                        chain = chain.strip().upper()
                        if chain:
                            # Normalize common network names
                            normalized = _normalize_network_name(chain)
                            if normalized:
                                available_networks.add(normalized)
                    
                    # Store as enabled (inverse of disabled)
                    _set_cached_status('Gate.io', currency, not deposit_disabled, not withdraw_disabled, available_networks)
                
                print(f"Cached {len(currencies)} Gate.io currency statuses")
        except Exception as e:
            print(f"Failed to batch fetch Gate.io currencies: {e}")
    
    def batch_fetch_binance_currencies():
        """Fetch all currency status from Binance using API keys if available"""
        try:
            import hmac
            import hashlib
            from urllib.parse import urlencode
            
            api_key = os.environ.get('BINANCE_API_KEY', '')
            api_secret = os.environ.get('BINANCE_API_SECRET', '')
            
            if not api_key or not api_secret:
                print("Binance API keys not found, skipping deposit/withdrawal status check")
                return
            
            # Create signed request for /sapi/v1/capital/config/getall
            timestamp = int(time.time() * 1000)
            params = {'timestamp': timestamp}
            query_string = urlencode(params)
            signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
            
            url = f'https://api.binance.com/sapi/v1/capital/config/getall?{query_string}&signature={signature}'
            req = _req.Request(url)
            req.add_header('X-MBX-APIKEY', api_key)
            
            with _req.urlopen(req, timeout=10) as r:
                coins = json.load(r)
                for coin in coins:
                    asset = coin.get('coin', '')
                    if asset:
                        deposit = coin.get('depositAllEnable', True)
                        withdraw = coin.get('withdrawAllEnable', True)
                        
                        # Extract networks
                        available_networks = set()
                        network_list = coin.get('networkList', [])
                        for net in network_list:
                            if net.get('depositEnable', False) and net.get('withdrawEnable', False):
                                network_name = net.get('network', '')
                                if network_name:
                                    # Normalize network names
                                    normalized = _normalize_network_name(network_name)
                                    if normalized:
                                        available_networks.add(normalized)
                        
                        _set_cached_status('Binance', asset, deposit, withdraw, available_networks)
                print(f"Cached {len(coins)} Binance currency statuses")
        except Exception as e:
            print(f"Failed to batch fetch Binance currencies: {e}")
    
    def batch_fetch_mexc_currencies():
        """Fetch all currency status from MEXC using API keys if available"""
        try:
            import hmac
            import hashlib
            from urllib.parse import urlencode
            
            api_key = os.environ.get('MEXC_API_KEY', '')
            api_secret = os.environ.get('MEXC_API_SECRET', '')
            
            if not api_key or not api_secret:
                print("MEXC API keys not found, skipping deposit/withdrawal status check")
                return
            
            # MEXC uses timestamp in milliseconds
            timestamp = int(time.time() * 1000)
            params = {
                'timestamp': timestamp
            }
            query_string = urlencode(params)
            signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
            
            # MEXC API endpoint for coin information
            url = f'https://api.mexc.com/api/v3/capital/config/getall?{query_string}&signature={signature}'
            req = _req.Request(url)
            req.add_header('X-MEXC-APIKEY', api_key)
            
            with _req.urlopen(req, timeout=10) as r:
                coins = json.load(r)
                for coin in coins:
                    asset = coin.get('coin', '')
                    if asset:
                        # MEXC uses networkList - need to check if ANY network supports deposit/withdraw
                        network_list = coin.get('networkList', [])
                        if network_list:
                            # Collect networks that support both deposit and withdraw
                            available_networks = set()
                            deposit_enabled = False
                            withdraw_enabled = False
                            
                            for net in network_list:
                                dep = net.get('depositEnable', False)
                                wit = net.get('withdrawEnable', False)
                                network_name = net.get('network', '') or net.get('netWork', '')
                                
                                if dep:
                                    deposit_enabled = True
                                if wit:
                                    withdraw_enabled = True
                                
                                # Store network if BOTH deposit and withdraw are enabled
                                if dep and wit and network_name:
                                    # Normalize network names
                                    normalized = _normalize_network_name(network_name)
                                    if normalized:
                                        available_networks.add(normalized)
                            
                            _set_cached_status('MEXC', asset, deposit_enabled, withdraw_enabled, available_networks)
                        else:
                            # Fallback to top-level flags (older API format)
                            deposit = coin.get('depositEnable', False) or coin.get('depositAllEnable', False)
                            withdraw = coin.get('withdrawEnable', False) or coin.get('withdrawAllEnable', False)
                            _set_cached_status('MEXC', asset, deposit, withdraw, set())
                print(f"Cached {len(coins)} MEXC currency statuses")
        except Exception as e:
            print(f"Failed to batch fetch MEXC currencies: {e}")
    
    def batch_fetch_bitget_currencies():
        """Fetch all currency status from Bitget"""
        try:
            # Bitget requires User-Agent header
            req = _req.Request('https://api.bitget.com/api/v2/spot/public/coins')
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', 'application/json')
            
            with _req.urlopen(req, timeout=10) as r:
                data = json.load(r)
                coins = data.get('data', [])
                for coin in coins:
                    asset = coin.get('coin', '')
                    if asset:
                        # Bitget uses 'chains' array with depositEnabled/withdrawEnabled per chain
                        # We check if ANY chain allows deposit/withdraw
                        chains = coin.get('chains', [])
                        deposit = any(c.get('depositEnable', '') == 'true' for c in chains)
                        withdraw = any(c.get('withdrawEnable', '') == 'true' for c in chains)
                        
                        # Extract available networks
                        available_networks = set()
                        for chain in chains:
                            if chain.get('depositEnable', '') == 'true' and chain.get('withdrawEnable', '') == 'true':
                                chain_name = chain.get('chain', '') or chain.get('chainName', '')
                                if chain_name:
                                    # Normalize network names
                                    normalized = _normalize_network_name(chain_name)
                                    if normalized:
                                        available_networks.add(normalized)
                        
                        _set_cached_status('Bitget', asset, deposit, withdraw, available_networks)
                print(f"Cached {len(coins)} Bitget currency statuses")
        except Exception as e:
            print(f"Failed to batch fetch Bitget currencies: {e}")
    
    def check_binance_deposit_withdraw_status(symbol):
        """Check if deposit/withdrawal is enabled for a symbol on Binance"""
        base_asset = symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')
        
        # Check cache first
        cached = _get_cached_status('Binance', base_asset)
        if cached:
            return cached
        
        # Not in cache, assume enabled (batch fetch will populate cache if API keys are available)
        _set_cached_status('Binance', base_asset, True, True)
        return {'deposit_enabled': True, 'withdraw_enabled': True}
    
    def check_mexc_deposit_withdraw_status(symbol):
        """Check if deposit/withdrawal is enabled for a symbol on MEXC"""
        base_asset = symbol.replace('USDT', '').replace('USDC', '')
        
        # Check cache first
        cached = _get_cached_status('MEXC', base_asset)
        if cached:
            return cached
        
        # Not in cache, assume enabled (batch fetch will populate cache if API keys are available)
        _set_cached_status('MEXC', base_asset, True, True)
        return {'deposit_enabled': True, 'withdraw_enabled': True}
    
    def check_gateio_deposit_withdraw_status(symbol):
        """Check if deposit/withdrawal is enabled for a symbol on Gate.io"""
        base_asset = symbol.replace('USDT', '').replace('USDC', '')
        
        # Check cache first
        cached = _get_cached_status('Gate.io', base_asset)
        if cached:
            return cached
        
        # Not in cache, assume enabled (batch fetch will populate cache)
        _set_cached_status('Gate.io', base_asset, True, True)
        return {'deposit_enabled': True, 'withdraw_enabled': True}
    
    def check_kucoin_deposit_withdraw_status(symbol):
        """Check if deposit/withdrawal is enabled for a symbol on KuCoin"""
        base_asset = symbol.replace('USDT', '').replace('USDC', '')
        
        # Check cache first
        cached = _get_cached_status('KuCoin', base_asset)
        if cached:
            return cached
        
        # Not in cache, assume enabled (batch fetch will populate cache)
        _set_cached_status('KuCoin', base_asset, True, True)
        return {'deposit_enabled': True, 'withdraw_enabled': True}
    
    def check_bitget_deposit_withdraw_status(symbol):
        """Check if deposit/withdrawal is enabled for a symbol on Bitget"""
        base_asset = symbol.replace('USDT', '').replace('USDC', '')
        
        # Check cache first
        cached = _get_cached_status('Bitget', base_asset)
        if cached:
            return cached
        
        # Not in cache, assume enabled (batch fetch will populate cache)
        _set_cached_status('Bitget', base_asset, True, True)
        return {'deposit_enabled': True, 'withdraw_enabled': True}
    
    try:
        # Batch fetch deposit/withdrawal status for all exchanges
        # These calls populate the cache with all currencies at once
        print("Batch fetching currency status from Binance, MEXC, KuCoin, Gate.io, and Bitget...")
        batch_fetch_binance_currencies()
        batch_fetch_mexc_currencies()
        batch_fetch_kucoin_currencies()
        batch_fetch_gateio_currencies()
        batch_fetch_bitget_currencies()
        
        # Fetch actively trading symbols on Binance and KuCoin
        binance_trading_symbols = fetch_binance_trading_symbols()
        kucoin_trading_symbols = fetch_kucoin_trading_symbols()
        
        # Fetch all tickers
        binance_data = fetch_binance_spot_tickers()
        mexc_data = fetch_mexc_spot_tickers()
        gateio_data = fetch_gateio_spot_tickers()
        kucoin_data = fetch_kucoin_spot_tickers()
        bitget_data = fetch_bitget_spot_tickers()
        
        # Build price maps for each exchange
        binance_prices = {}
        for t in binance_data:
            symbol = t.get('symbol', '')
            if not symbol.endswith('USDT'):
                continue
            # Filter out leveraged ETF products (3S/3L tokens)
            if symbol.endswith('3SUSDT') or symbol.endswith('3LUSDT'):
                continue
            # Filter out symbols that are not actively trading (status != TRADING)
            if symbol not in binance_trading_symbols:
                continue
            try:
                price = float(t.get('lastPrice', 0))
                volume = float(t.get('quoteVolume', 0))
                if price > 0 and volume > 10000:  # Min $10k volume
                    binance_prices[symbol] = {
                        'price': price,
                        'volume': volume,
                        'exchange': 'Binance'
                    }
            except:
                pass
        
        mexc_prices = {}
        for t in mexc_data:
            symbol = t.get('symbol', '')
            if not symbol.endswith('USDT'):
                continue
            # Filter out leveraged ETF products
            if symbol.endswith('3SUSDT') or symbol.endswith('3LUSDT'):
                continue
            try:
                price = float(t.get('lastPrice', 0))
                volume = float(t.get('quoteVolume', 0))
                if price > 0 and volume > 10000:
                    mexc_prices[symbol] = {
                        'price': price,
                        'volume': volume,
                        'exchange': 'MEXC'
                    }
            except:
                pass
        
        gateio_prices = {}
        for t in gateio_data:
            currency_pair = t.get('currency_pair', '')
            if not currency_pair.endswith('_USDT'):
                continue
            symbol = currency_pair.replace('_', '')  # Convert BTC_USDT to BTCUSDT
            # Filter out leveraged ETF products
            if symbol.endswith('3SUSDT') or symbol.endswith('3LUSDT'):
                continue
            try:
                price = float(t.get('last', 0))
                volume = float(t.get('quote_volume', 0))
                if price > 0 and volume > 10000:
                    gateio_prices[symbol] = {
                        'price': price,
                        'volume': volume,
                        'exchange': 'Gate.io'
                    }
            except:
                pass
        
        kucoin_prices = {}
        for t in kucoin_data:
            symbol_raw = t.get('symbol', '')
            if not symbol_raw.endswith('-USDT'):
                continue
            symbol = symbol_raw.replace('-', '')  # Convert BTC-USDT to BTCUSDT
            # Filter out leveraged ETF products
            if symbol.endswith('3SUSDT') or symbol.endswith('3LUSDT'):
                continue
            # Filter out symbols that are not actively trading (enableTrading=false)
            if symbol not in kucoin_trading_symbols:
                continue
            try:
                price = float(t.get('last', 0))
                volume = float(t.get('volValue', 0))
                if price > 0 and volume > 10000:
                    kucoin_prices[symbol] = {
                        'price': price,
                        'volume': volume,
                        'exchange': 'KuCoin'
                    }
            except:
                pass
        
        bitget_prices = {}
        for t in bitget_data:
            symbol = t.get('symbol', '')
            if not symbol.endswith('USDT'):
                continue
            # Filter out leveraged ETF products
            if symbol.endswith('3SUSDT') or symbol.endswith('3LUSDT'):
                continue
            try:
                price = float(t.get('lastPr', 0))
                volume = float(t.get('quoteVolume', 0))
                if price > 0 and volume > 10000:
                    bitget_prices[symbol] = {
                        'price': price,
                        'volume': volume,
                        'exchange': 'Bitget'
                    }
            except Exception as e:
                # Only print first few errors to avoid spam
                if len(bitget_prices) < 3:
                    print(f"Bitget parse error for {symbol}: {e}")
        
        print(f"Parsed {len(bitget_prices)} Bitget prices (sample: {list(bitget_prices.keys())[:5]})")
        
        # Find arbitrage opportunities
        opportunities = []
        
        # Get all unique symbols across all exchanges
        all_symbols = set()
        all_symbols.update(binance_prices.keys())
        all_symbols.update(mexc_prices.keys())
        all_symbols.update(gateio_prices.keys())
        all_symbols.update(kucoin_prices.keys())
        all_symbols.update(bitget_prices.keys())
        
        for symbol in all_symbols:
            prices_by_exchange = []
            
            if symbol in binance_prices:
                prices_by_exchange.append(binance_prices[symbol])
            if symbol in mexc_prices:
                prices_by_exchange.append(mexc_prices[symbol])
            if symbol in gateio_prices:
                prices_by_exchange.append(gateio_prices[symbol])
            if symbol in kucoin_prices:
                prices_by_exchange.append(kucoin_prices[symbol])
            if symbol in bitget_prices:
                prices_by_exchange.append(bitget_prices[symbol])
            
            # Need at least 2 exchanges to arbitrage
            if len(prices_by_exchange) < 2:
                continue
            
            # Find min and max prices
            sorted_prices = sorted(prices_by_exchange, key=lambda x: x['price'])
            lowest = sorted_prices[0]
            highest = sorted_prices[-1]
            
            spread_pct = ((highest['price'] - lowest['price']) / lowest['price']) * 100
            
            # Filter realistic spreads: >0.5% but <10% (anything higher is likely data error)
            # Also ensure prices are within 20% of each other (prevent comparing different pairs)
            price_deviation = ((highest['price'] - lowest['price']) / statistics.mean([p['price'] for p in prices_by_exchange])) * 100
            
            if 0.5 < spread_pct < 10 and price_deviation < 20:
                # Additional validation: all prices should be within reasonable range
                min_price = min(p['price'] for p in prices_by_exchange)
                max_price = max(p['price'] for p in prices_by_exchange)
                
                # Skip if price difference ratio is too extreme (likely different pairs)
                if max_price / min_price > 1.15:  # Max 15% difference
                    continue
                
                total_volume = sum(p['volume'] for p in prices_by_exchange)
                avg_price = statistics.mean(p['price'] for p in prices_by_exchange)
                
                # Check deposit/withdrawal status
                buy_status = {'deposit_enabled': True, 'withdraw_enabled': True}
                sell_status = {'deposit_enabled': True, 'withdraw_enabled': True}
                
                if lowest['exchange'] == 'Binance':
                    buy_status = check_binance_deposit_withdraw_status(symbol)
                elif lowest['exchange'] == 'MEXC':
                    buy_status = check_mexc_deposit_withdraw_status(symbol)
                elif lowest['exchange'] == 'Gate.io':
                    buy_status = check_gateio_deposit_withdraw_status(symbol)
                elif lowest['exchange'] == 'KuCoin':
                    buy_status = check_kucoin_deposit_withdraw_status(symbol)
                elif lowest['exchange'] == 'Bitget':
                    buy_status = check_bitget_deposit_withdraw_status(symbol)
                
                if highest['exchange'] == 'Binance':
                    sell_status = check_binance_deposit_withdraw_status(symbol)
                elif highest['exchange'] == 'MEXC':
                    sell_status = check_mexc_deposit_withdraw_status(symbol)
                elif highest['exchange'] == 'Gate.io':
                    sell_status = check_gateio_deposit_withdraw_status(symbol)
                elif highest['exchange'] == 'KuCoin':
                    sell_status = check_kucoin_deposit_withdraw_status(symbol)
                elif highest['exchange'] == 'Bitget':
                    sell_status = check_bitget_deposit_withdraw_status(symbol)
                
                # Check if arbitrage is executable (withdraw from buy exchange, deposit to sell exchange)
                # Also verify they have at least one common network for transfers
                base_asset = symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')
                has_common_network = _check_common_networks(lowest['exchange'], highest['exchange'], base_asset)
                is_executable = buy_status['withdraw_enabled'] and sell_status['deposit_enabled'] and has_common_network
                
                # Calculate realistic PnL with $100 notional
                pnl = calculate_arbitrage_pnl(
                    symbol=symbol,
                    buy_price=lowest['price'],
                    sell_price=highest['price'],
                    buy_exchange=lowest['exchange'],
                    sell_exchange=highest['exchange'],
                    notional=100
                )
                
                opportunities.append({
                    'symbol': symbol,
                    'buy_exchange': lowest['exchange'],
                    'buy_price': lowest['price'],
                    'buy_volume': lowest['volume'],
                    'buy_withdraw_enabled': buy_status['withdraw_enabled'],
                    'sell_exchange': highest['exchange'],
                    'sell_price': highest['price'],
                    'sell_volume': highest['volume'],
                    'sell_deposit_enabled': sell_status['deposit_enabled'],
                    'spread_pct': spread_pct,
                    'avg_price': avg_price,
                    'total_volume': total_volume,
                    'exchanges_available': len(prices_by_exchange),
                    'is_executable': is_executable,
                    'profitability': 'high' if spread_pct > 2 else 'medium' if spread_pct > 1 else 'low',
                    # PnL breakdown for $100 trade
                    'net_profit_usd': pnl['net_profit_usd'],
                    'roi_percent': pnl['roi_percent'],
                    'trading_fees_usd': pnl['trading_fees_usd'],
                    'withdrawal_fee_usd': pnl['withdrawal_fee_usd'],
                    'slippage_cost_usd': pnl['slippage_cost_usd'],
                    'is_profitable_after_fees': pnl['is_profitable']
                })
        
        # Sort by spread percentage (highest first)
        opportunities.sort(key=lambda x: x['spread_pct'], reverse=True)
        
        # Separate executable and blocked opportunities
        executable_opps = [o for o in opportunities if o.get('is_executable', True)]
        blocked_opps = [o for o in opportunities if not o.get('is_executable', True)]
        
        return {
            'opportunities': opportunities[:50],  # Top 50 opportunities (all)
            'executable_opportunities': executable_opps[:50],  # Executable only
            'blocked_opportunities': blocked_opps[:20],  # Top 20 blocked
            'total_symbols_scanned': len(all_symbols),
            'timestamp': time.time()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'spot-arbitrage-scan-failed: {str(e)}')

# -----------------------------------------------------------------------------
# In-memory state
# -----------------------------------------------------------------------------
server_logs: list[dict] = []
latest_opportunities: Optional[dict] = None  # store {'opportunities': [...]}
_scanner_task: Optional[asyncio.Task] = None
_hotcoins_task: Optional[asyncio.Task] = None
_vol_index_task: Optional[asyncio.Task] = None
_position_monitor_task: Optional[asyncio.Task] = None
manager = ConnectionManager()
hot_manager = ConnectionManager()
liquidation_manager = ConnectionManager()
_ccxt_instances: Dict[str, object] = {}

# In-memory buffer of recent liquidation events (dicts with ts (ISO), msg)
from collections import deque, defaultdict
_liquidation_buffer: deque = deque(maxlen=20000)

# Cached hotcoins per-minute aggregates to avoid expensive per-request work.
_hot_by_minute_cache: dict = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'base_vol': 0.0, 'quote_vol': 0.0}))
_hot_by_minute_lock: asyncio.Lock = asyncio.Lock()
# minutes window to precompute (env ARB_HOT_AGG_WINDOW_MIN)
_hot_by_minute_window_min: int = int(os.environ.get('ARB_HOT_AGG_WINDOW_MIN', '120'))
_hotcoins_agg_task: Optional[asyncio.Task] = None
_hotcoins_agg_last_ts: Optional[str] = None
_hotcoins_agg_last_hot_list: list = []

# In-memory recent price history for hotcoins: symbol -> deque of (ts_iso, price)
from collections import deque as _deque
_hot_price_history: Dict[str, _deque] = defaultdict(lambda: _deque(maxlen=3600))
# Lock for safety when updating history
_hot_price_history_lock: asyncio.Lock = asyncio.Lock()
# Alerting controls
_hot_percent_window_min: int = int(os.environ.get('ARB_HOT_ALERT_WINDOW_MIN', '15'))
_hot_percent_threshold: float = float(os.environ.get('ARB_HOT_ALERT_PCT', '5.0'))
# Track last alert time per symbol to avoid spamming (ISO ts)
_hot_last_alert_ts: Dict[str, str] = {}

# Feature extractor / alert webhook control
_feature_extractor = None
_alerts_enabled: bool = False
try:
    from .analytics.feature_extractor import FeatureExtractor
    try:
        _feature_extractor = FeatureExtractor(['binance', 'kucoin', 'mexc'])
    except Exception:
        _feature_extractor = None
except Exception:
    _feature_extractor = None

# persisted config path for webhook
_config_path = os.path.join(ROOT, 'var', 'webhook_config.json')
os.makedirs(os.path.dirname(_config_path), exist_ok=True)

def _load_webhook_config():
    try:
        if os.path.exists(_config_path):
            with open(_config_path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


# Live strategy manager - support multiple concurrent strategies
_live_strategy_instances = {}  # key: symbol, value: LiveStrategy instance


@app.get('/api/defi-vaults')
def get_defi_vaults():
    """Get DeFi stablecoin lending vaults with APY data from DeFiLlama API.
    
    Returns vault information for stablecoin looping strategies across:
    - Morpho, Aave, Compound (Ethereum)
    - Venus (BSC)
    - Benqi (Avalanche)
    """
    from urllib import request as _req
    import json as js
    
    vaults = []
    
    # Fetch real-time data from DeFiLlama Yields API
    try:
        # Fetch pools data from DeFiLlama
        print("[DEBUG] Starting DeFiLlama API request...")
        req = _req.Request('https://yields.llama.fi/pools')
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        with _req.urlopen(req, timeout=10) as resp:
            print(f"[DEBUG] API response status: {resp.status}")
            data = js.loads(resp.read().decode('utf-8'))
            
        pools = data.get('data', [])
        print(f"[DEBUG] Fetched {len(pools)} pools from DeFiLlama API")
        
        # Filter for TOP stablecoin lending pools with:
        # - High base APY (not just rewards)
        # - Minimum $10M TVL for safety
        # - Stablecoins only (USDC, USDT, DAI, USR, etc.)
        # - Major chains: Ethereum, BSC, Avalanche, Arbitrum, Optimism
        
        MIN_TVL = 10_000_000  # $10M minimum TVL
        MIN_BASE_APY = 10.0   # 10% minimum base APY (not counting rewards)
        
        filtered_pools = []
        for pool in pools:
            # Must be stablecoin lending pool (no impermanent loss risk)
            if pool.get('ilRisk') != 'no' or pool.get('stablecoin') != True:
                continue
            
            # Handle None values properly - use 0 as default for numeric comparisons
            apy = pool.get('apy') if pool.get('apy') is not None else 0
            apy_base = pool.get('apyBase') if pool.get('apyBase') is not None else 0
            tvl = pool.get('tvlUsd') if pool.get('tvlUsd') is not None else 0
            chain = pool.get('chain', '')
            
            # Filter criteria:
            # 1. TVL >= $10M (liquid, established pools)
            # 2. Base APY >= 10% (real yield, not just incentives)
            # 3. Base APY is at least 70% of total APY (not reward-driven)
            if tvl >= MIN_TVL and apy_base >= MIN_BASE_APY:
                # Ensure base APY is the primary driver (not just reward tokens)
                if apy_base / apy >= 0.7 if apy > 0 else True:
                    filtered_pools.append({
                        'pool': pool,
                        'protocol': pool.get('project', '').lower(),
                        'chain': chain,
                        'symbol': pool.get('symbol', '').upper(),
                        'apy': apy,
                        'apy_base': apy_base,
                        'tvl': tvl
                    })
        
        # Sort by base APY (not total APY) to prioritize sustainable yields
        filtered_pools.sort(key=lambda x: x['apy_base'], reverse=True)
        print(f"[DEBUG] Filtered to {len(filtered_pools)} pools with $10M+ TVL and 10%+ base APY")
        
        # Take top 4 pools only - best high-yield opportunities with solid TVL
        top_pools = filtered_pools[:4]
        print(f"[DEBUG] Selected top {len(top_pools)} pools for display")
        
        # Create vault entries from top pools
        for item in top_pools:
            pool = item['pool']
            protocol_name = pool.get('project', '').replace('-', ' ').title()
            
            # Determine primary asset and get the full symbol for clarity
            symbol = pool.get('symbol', '')
            asset = 'USDC'
            if 'USDT' in symbol:
                asset = 'USDT'
            elif 'USR' in symbol:
                asset = 'USR'
            elif 'DAI' in symbol:
                asset = 'DAI'
            elif 'SUSD' in symbol:
                asset = 'sUSD'
            elif 'ASUSD' in symbol:
                asset = 'ASUSD'
            
            # Use the actual symbol from DeFiLlama for the vault name (e.g., REUSDC, AUSDC)
            # This helps distinguish between different markets/wrappers
            vault_symbol = symbol if symbol else asset
            
            # Determine risk level based on TVL and protocol
            # Use the already-sanitized value from filtered_pools
            tvl = item['tvl']
            if tvl > 100000000:  # >$100M TVL
                risk_level = 'Low'
            elif tvl > 50000000:  # >$50M TVL
                risk_level = 'Low-Medium'
            elif tvl > 20000000:  # >$20M TVL
                risk_level = 'Medium'
            else:
                risk_level = 'Medium'
            
            # Map protocol names to friendly display names
            protocol_map = {
                'morpho-blue': 'Morpho',
                'aave-v3': 'Aave',
                'compound-v3': 'Compound',
                'venus': 'Venus',
                'benqi': 'Benqi',
                'pendle': 'Pendle',
                'hyperion': 'Hyperion',
                'etherex': 'Etherex',
                'peapods': 'Peapods Finance'
            }
            
            mapped_protocol = protocol_map.get(pool.get('project', ''), protocol_name)
            
            # Create unique ID using pool ID to ensure uniqueness
            vault_id = pool.get('pool', '')

            
            # Build detailed description showing APY breakdown
            # Use the already-sanitized values from filtered_pools
            apy_base = item['apy_base']
            apy_reward = pool.get('apyReward') if pool.get('apyReward') is not None else 0
            apy_mean_30d = pool.get('apyMean30d') if pool.get('apyMean30d') is not None else 0
            pool_meta = pool.get('poolMeta', '')
            
            # Get predictions if available
            predictions = pool.get('predictions', {})
            pred_direction = predictions.get('predictedClass', '')
            pred_probability = predictions.get('predictedProbability', 0)
            
            description_parts = []
            
            # Add APY breakdown
            if apy_base > 0 and apy_reward > 0:
                description_parts.append(f"Base APY: {apy_base:.2f}% + Rewards: {apy_reward:.2f}%")
            elif apy_base > 0:
                description_parts.append(f"APY: {apy_base:.2f}%")
            
            # Show 30-day average if significantly different from current
            if apy_mean_30d > 0 and abs(apy_base - apy_mean_30d) / apy_mean_30d > 0.2:
                description_parts.append(f"30d Avg: {apy_mean_30d:.2f}%")
            
            if pool_meta:
                description_parts.append(f"Pool: {pool_meta}")
            
            # Add strategy explanation for high APY
            # Use the sanitized APY value from item
            current_apy = item['apy']
            if current_apy > 50:
                description_parts.append("⚡ Leveraged looping strategy (4x+)")
                if pred_direction == 'Down' and pred_probability > 80:
                    description_parts.append(f"⚠️ APY predicted to decline (30d avg: {apy_mean_30d:.1f}%)")
            elif current_apy > 20:
                description_parts.append("⚡ Automated leverage/looping")
                if pred_direction == 'Down' and pred_probability > 80:
                    description_parts.append(f"⚠️ APY may decrease soon")
            
            description_parts.append(f"Supply {asset} via {mapped_protocol} on {pool.get('chain', '')}")
            
            description = " | ".join(description_parts)
            
            # Determine if leveraged and calculate risk metrics
            pool_meta_str = pool.get('poolMeta') or ''
            is_leveraged = current_apy > 20 or 'loop' in pool_meta_str.lower()
            
            # Estimate leverage ratio from APY (rough approximation)
            # Higher APY typically means higher leverage
            leverage_ratio = 1.0
            liquidation_ltv = None
            max_ltv = None
            
            if is_leveraged:
                # Rough estimates based on common DeFi protocols
                if current_apy > 50:
                    leverage_ratio = 4.0  # ~4x leverage
                    max_ltv = 0.85  # 85% LTV
                    liquidation_ltv = 0.88  # 88% liquidation threshold
                elif current_apy > 30:
                    leverage_ratio = 3.0  # ~3x leverage
                    max_ltv = 0.80
                    liquidation_ltv = 0.85
                elif current_apy > 20:
                    leverage_ratio = 2.0  # ~2x leverage
                    max_ltv = 0.75
                    liquidation_ltv = 0.80
            
            # Get protocol URL for viewing
            pool_id = pool.get('pool', '')
            project_slug = pool.get('project', '')
            chain_slug = pool.get('chain', '').lower()
            
            # Always use DeFiLlama as primary URL since it shows the actual pool data
            # This ensures users see the same APY/TVL that we're displaying
            vault_url = f"https://defillama.com/yields/pool/{pool_id}"
            
            # Store protocol-specific URLs as additional links
            protocol_url = None
            if 'morpho' in project_slug:
                protocol_url = "https://app.morpho.org/?network=mainnet"
            elif 'aave' in project_slug:
                protocol_url = "https://app.aave.com/"
            elif 'compound' in project_slug:
                protocol_url = "https://app.compound.finance/"
            elif 'benqi' in project_slug:
                protocol_url = "https://app.benqi.fi/"
            elif 'venus' in project_slug:
                protocol_url = "https://app.venus.io/"
            
            # Additional metrics from DeFiLlama
            apy_pct_1d = pool.get('apyPct1D')
            apy_pct_7d = pool.get('apyPct7D')
            apy_pct_30d = pool.get('apyPct30D')
            apy_base_7d = pool.get('apyBase7d')
            apy_base_inception = pool.get('apyBaseInception')
            volume_1d = pool.get('volumeUsd1d')
            volume_7d = pool.get('volumeUsd7d')
            outlier = pool.get('outlier', False)
            exposure = pool.get('exposure', 'single')
            underlying_tokens = pool.get('underlyingTokens', [])
            
            vaults.append({
                'id': vault_id,
                'name': f"{mapped_protocol} {vault_symbol}",  # Use actual symbol (e.g., REUSDC) not just generic asset
                'protocol': mapped_protocol,
                'chain': pool.get('chain', 'Ethereum'),
                'asset': asset,
                'strategy': 'Lending' if 'aave' in pool.get('project', '') or 'compound' in pool.get('project', '') else 'Looping',
                'apy': round(item['apy'], 2),
                'target_apy': round(item['apy'] * 1.2, 2),  # 20% above current as target
                'tvl_usd': int(tvl),
                'risk_level': risk_level,
                # Note: DeFiLlama API does not provide fee or withdrawal period data
                # These would need to be fetched from protocol-specific sources
                'withdrawal_period_days': None,  # Not available from API
                'platform_fee': None,  # Not available from API
                'performance_fee': None,  # Not available from API
                'description': description,
                'vault_address': pool.get('pool', '0x...'),
                'active': True,
                'apy_base': round(apy_base, 2),
                'apy_reward': round(apy_reward, 2),
                'apy_mean_30d': round(apy_mean_30d, 2) if apy_mean_30d > 0 else None,
                'apy_base_7d': round(apy_base_7d, 2) if apy_base_7d else None,
                'apy_base_inception': round(apy_base_inception, 2) if apy_base_inception else None,
                'apy_pct_1d': round(apy_pct_1d, 2) if apy_pct_1d is not None else None,
                'apy_pct_7d': round(apy_pct_7d, 2) if apy_pct_7d is not None else None,
                'apy_pct_30d': round(apy_pct_30d, 2) if apy_pct_30d is not None else None,
                'apy_prediction': pred_direction if pred_direction else None,
                'apy_prediction_confidence': pred_probability if pred_probability > 0 else None,
                'pool_meta': pool_meta,
                'is_leveraged': is_leveraged,
                'leverage_ratio': leverage_ratio,
                'max_ltv': max_ltv,
                'liquidation_ltv': liquidation_ltv,
                'volume_usd_1d': int(volume_1d) if volume_1d else None,
                'volume_usd_7d': int(volume_7d) if volume_7d else None,
                'outlier': outlier,  # Flag for potentially unsustainable yields
                'exposure': exposure,  # 'single' for single asset, 'multi' for LP
                'underlying_tokens': underlying_tokens,
                'vault_url': vault_url,
                'protocol_url': protocol_url,
                'defillama_url': f"https://defillama.com/yields/pool/{pool_id}"
            })
        
        print(f"[DEBUG] Created {len(vaults)} vault entries from DeFiLlama data")
        
        # If no pools found from API, fall back to curated mock data
        if len(vaults) == 0:
            print("[DEBUG] No vaults created from API, using fallback")
            raise Exception("No pools from API, using fallback")
        
        print(f"[DEBUG] Successfully returning {len(vaults)} live vaults from DeFiLlama")
        
    except Exception as e:
        print(f"Warning: Could not fetch from DeFiLlama API ({e}), using curated vaults")
        import traceback
        traceback.print_exc()
        vaults = []
        
        # Morpho Blue - USDC
        # NOTE: Fallback mock data - fee/withdrawal data is estimated/unknown
        vaults.append({
            'id': 'morpho-usdc-eth',
            'name': 'Morpho USDC Optimizer',
            'protocol': 'Morpho',
            'chain': 'Ethereum',
            'asset': 'USDC',
            'strategy': 'Looping',
            'apy': 8.5,
            'target_apy': 12.0,
            'tvl_usd': 45000000,
            'risk_level': 'Low',
            'withdrawal_period_days': None,  # Unknown - not in API
            'platform_fee': None,  # Unknown - not in API
            'performance_fee': None,  # Unknown - not in API
            'description': 'Automated USDC looping on Morpho with optimized yields',
            'vault_address': '0x...',
            'active': True,
            'apy_base': 8.5,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Aave V3 - USDT
        vaults.append({
            'id': 'aave-usdt-eth',
            'name': 'Aave V3 USDT Yield',
            'protocol': 'Aave',
            'chain': 'Ethereum',
            'asset': 'USDT',
            'strategy': 'Looping',
            'apy': 6.8,
            'target_apy': 10.0,
            'tvl_usd': 120000000,
            'risk_level': 'Low',
            'withdrawal_period_days': None,
            'platform_fee': None,
            'performance_fee': None,
            'description': 'Supply USDT to Aave V3 with automated looping',
            'vault_address': '0x...',
            'active': True,
            'apy_base': 6.8,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Compound V3 - USDC
        vaults.append({
            'id': 'compound-usdc-eth',
            'name': 'Compound USDC Vault',
            'protocol': 'Compound',
            'chain': 'Ethereum',
            'asset': 'USDC',
            'strategy': 'Looping',
            'apy': 7.2,
            'target_apy': 11.0,
            'tvl_usd': 85000000,
            'risk_level': 'Low',
            'withdrawal_period_days': None,
            'platform_fee': None,
            'performance_fee': None,
            'description': 'Optimized USDC supply on Compound V3',
            'vault_address': '0x...',
            'active': True,
            'apy_base': 7.2,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Resolv USR Yield Maxi (from your screenshot)
        vaults.append({
            'id': 'resolv-usr-maxi',
            'name': 'Resolv USR Yield Maxi',
            'protocol': 'Resolv',
            'chain': 'Ethereum',
            'asset': 'USR',
            'strategy': 'Looping',
            'apy': 15.0,
            'target_apy': 15.0,
            'tvl_usd': 25000000,
            'risk_level': 'Medium',
            'withdrawal_period_days': None,  # Known from docs: 4 days, but keeping None for consistency
            'platform_fee': None,
            'performance_fee': None,
            'description': 'Systematically optimizes USR returns by executing looping strategies on prime lending markets including Morpho, Euler, Fluid and Gearbox',
            'vault_address': '0xdA89...E79e7D',
            'strategist': 'M1 Capital',
            'active': True,
            'apy_base': 15.0,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Venus Protocol - USDT (BSC)
        vaults.append({
            'id': 'venus-usdt-bsc',
            'name': 'Venus USDT Strategy',
            'protocol': 'Venus',
            'chain': 'BSC',
            'asset': 'USDT',
            'strategy': 'Looping',
            'apy': 5.5,
            'target_apy': 8.0,
            'tvl_usd': 65000000,
            'risk_level': 'Low',
            'withdrawal_period_days': None,
            'platform_fee': None,
            'performance_fee': None,
            'description': 'Supply USDT on Venus Protocol (BSC) with auto-compounding',
            'vault_address': '0x...',
            'active': True,
            'apy_base': 5.5,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Benqi - USDC (Avalanche)
        vaults.append({
            'id': 'benqi-usdc-avax',
            'name': 'Benqi USDC Vault',
            'protocol': 'Benqi',
            'chain': 'Avalanche',
            'asset': 'USDC',
            'strategy': 'Looping',
            'apy': 6.0,
            'target_apy': 9.0,
            'tvl_usd': 40000000,
            'risk_level': 'Low',
            'withdrawal_period_days': None,
            'platform_fee': None,
            'performance_fee': None,
            'description': 'Avalanche USDC lending with automated yield optimization',
            'vault_address': '0x...',
            'active': True,
            'apy_base': 6.0,
            'apy_reward': 0.0,
            'outlier': False
        })
        
        # Sort by APY (highest first)
        vaults.sort(key=lambda x: x['apy'], reverse=True)
    
    # Return vault data
    return {
        'vaults': vaults,
        'total_vaults': len(vaults),
        'total_tvl_usd': sum(v['tvl_usd'] for v in vaults),
        'avg_apy': sum(v['apy'] for v in vaults) / len(vaults) if vaults else 0,
        'timestamp': _dt.datetime.utcnow().isoformat()
    }


# -----------------------------------------------------------------------------
# DeFi Vault APY Monitoring & Alerts
# -----------------------------------------------------------------------------
_vault_apy_history = {}  # {pool_id: [{'timestamp': ..., 'apy': ..., 'apy_base': ...}, ...]}
_vault_alerts = {}  # {alert_id: {'pool_id': ..., 'threshold_type': ..., 'threshold_value': ..., 'active': True}}
_user_positions = {}  # {user_id: [{'pool_id': ..., 'amount': ..., 'entry_apy': ...}]}

@app.get('/api/defi-vaults/history/{pool_id}')
def get_vault_apy_history(pool_id: str, hours: int = 24):
    """Get APY history for a specific vault over the last N hours.
    
    Args:
        pool_id: The vault/pool ID from DeFiLlama
        hours: Number of hours of history to return (default: 24)
    
    Returns:
        Historical APY data points with timestamps
    """
    history = _vault_apy_history.get(pool_id, [])
    cutoff_time = time.time() - (hours * 3600)
    
    # Filter to requested time window
    recent_history = [h for h in history if h['timestamp'] >= cutoff_time]
    
    if not recent_history:
        return {
            'pool_id': pool_id,
            'history': [],
            'current_apy': None,
            'apy_change_24h': None,
            'message': 'No historical data available yet'
        }
    
    # Calculate APY change
    current = recent_history[-1] if recent_history else None
    oldest = recent_history[0] if len(recent_history) > 1 else None
    
    apy_change = None
    if current and oldest and oldest.get('apy'):
        apy_change = current.get('apy', 0) - oldest.get('apy', 0)
    
    return {
        'pool_id': pool_id,
        'history': recent_history,
        'current_apy': current.get('apy') if current else None,
        'current_apy_base': current.get('apy_base') if current else None,
        'apy_change': apy_change,
        'data_points': len(recent_history),
        'timestamp': _dt.datetime.utcnow().isoformat()
    }


@app.post('/api/defi-vaults/alerts')
async def create_vault_alert(req: Request):
    """Create an alert for APY changes on a specific vault.
    
    Body:
        {
            "pool_id": "morpho-blue-...",
            "alert_type": "apy_drop" | "apy_spike" | "apy_below" | "apy_above",
            "threshold": 10.0,  # Percentage or absolute value depending on type
            "notification_method": "webhook" | "email",
            "webhook_url": "https://...",  # Required if method is webhook
            "email": "user@example.com"  # Required if method is email
        }
    
    Alert Types:
        - apy_drop: Alert when APY drops by threshold % (e.g., -20% from current)
        - apy_spike: Alert when APY increases by threshold % (e.g., +50%)
        - apy_below: Alert when APY falls below threshold value
        - apy_above: Alert when APY rises above threshold value
    """
    body = await req.json()
    
    pool_id = body.get('pool_id', '').strip()
    alert_type = body.get('alert_type', '').strip()
    threshold = body.get('threshold')
    notification_method = body.get('notification_method', 'webhook')
    
    if not pool_id or not alert_type or threshold is None:
        raise HTTPException(status_code=400, detail='pool_id, alert_type, and threshold required')
    
    if alert_type not in ['apy_drop', 'apy_spike', 'apy_below', 'apy_above']:
        raise HTTPException(status_code=400, detail='Invalid alert_type')
    
    # Generate alert ID
    import hashlib
    alert_id = hashlib.md5(f"{pool_id}:{alert_type}:{threshold}:{time.time()}".encode()).hexdigest()[:16]
    
    # Store alert configuration
    _vault_alerts[alert_id] = {
        'alert_id': alert_id,
        'pool_id': pool_id,
        'alert_type': alert_type,
        'threshold': threshold,
        'notification_method': notification_method,
        'webhook_url': body.get('webhook_url'),
        'email': body.get('email'),
        'created_at': time.time(),
        'last_triggered': None,
        'trigger_count': 0,
        'active': True
    }
    
    return {
        'success': True,
        'alert_id': alert_id,
        'message': f'Alert created for {pool_id}',
        'alert': _vault_alerts[alert_id]
    }


@app.get('/api/defi-vaults/alerts')
def get_vault_alerts(active_only: bool = True):
    """Get all configured vault alerts."""
    alerts = list(_vault_alerts.values())
    
    if active_only:
        alerts = [a for a in alerts if a.get('active')]
    
    return {
        'alerts': alerts,
        'total_alerts': len(alerts),
        'timestamp': _dt.datetime.utcnow().isoformat()
    }


@app.delete('/api/defi-vaults/alerts/{alert_id}')
def delete_vault_alert(alert_id: str):
    """Delete/deactivate a vault alert."""
    if alert_id not in _vault_alerts:
        raise HTTPException(status_code=404, detail='Alert not found')
    
    _vault_alerts[alert_id]['active'] = False
    
    return {
        'success': True,
        'message': f'Alert {alert_id} deactivated'
    }


@app.post('/api/defi-vaults/positions')
async def track_user_position(req: Request):
    """Track a user's position in a DeFi vault for monitoring.
    
    Body:
        {
            "user_id": "0x...",  # Wallet address or user identifier
            "pool_id": "morpho-blue-...",
            "amount": 10000,  # USD value of position
            "entry_apy": 15.2,  # APY when position was entered
            "tx_hash": "0x...",  # Optional: transaction hash for verification
        }
    """
    body = await req.json()
    
    user_id = body.get('user_id', '').strip()
    pool_id = body.get('pool_id', '').strip()
    amount = body.get('amount')
    entry_apy = body.get('entry_apy')
    
    if not user_id or not pool_id or amount is None or entry_apy is None:
        raise HTTPException(status_code=400, detail='user_id, pool_id, amount, and entry_apy required')
    
    # Initialize user positions if needed
    if user_id not in _user_positions:
        _user_positions[user_id] = []
    
    # Add position
    position = {
        'pool_id': pool_id,
        'amount': amount,
        'entry_apy': entry_apy,
        'entry_timestamp': time.time(),
        'tx_hash': body.get('tx_hash'),
        'active': True
    }
    
    _user_positions[user_id].append(position)
    
    return {
        'success': True,
        'message': f'Position tracked for {user_id}',
        'position': position,
        'total_positions': len(_user_positions[user_id])
    }


@app.get('/api/defi-vaults/positions/{user_id}')
def get_user_positions(user_id: str):
    """Get all tracked positions for a user with current APY comparison."""
    positions = _user_positions.get(user_id, [])
    
    # Enrich with current APY data
    enriched_positions = []
    for pos in positions:
        if not pos.get('active'):
            continue
            
        pool_id = pos['pool_id']
        history = _vault_apy_history.get(pool_id, [])
        current_data = history[-1] if history else None
        
        current_apy = current_data.get('apy') if current_data else None
        apy_delta = (current_apy - pos['entry_apy']) if current_apy else None
        
        enriched_positions.append({
            **pos,
            'current_apy': current_apy,
            'apy_delta': apy_delta,
            'apy_delta_pct': (apy_delta / pos['entry_apy'] * 100) if apy_delta is not None else None
        })
    
    return {
        'user_id': user_id,
        'positions': enriched_positions,
        'total_positions': len(enriched_positions),
        'timestamp': _dt.datetime.utcnow().isoformat()
    }


@app.get('/api/wallet/balance/{address}')
async def get_wallet_balance(address: str, chains: str = 'ethereum,bsc,polygon,arbitrum,optimism,base,avalanche'):
    """
    Get Web3 wallet balance across multiple chains.
    Uses public RPC endpoints to fetch native token balances and ERC20 token balances.
    
    Query params:
        chains: Comma-separated list of chains (default: ethereum,bsc,polygon,arbitrum,optimism,base,avalanche)
    """
    try:
        import requests
        from decimal import Decimal
        
        chain_list = [c.strip().lower() for c in chains.split(',')]
        
        # RPC endpoints and native token info
        chain_config = {
            'ethereum': {
                'rpc': 'https://eth.llamarpc.com',
                'native': 'ETH',
                'decimals': 18,
                'coingecko_id': 'ethereum'
            },
            'bsc': {
                'rpc': 'https://bsc-dataseed1.binance.org',
                'native': 'BNB',
                'decimals': 18,
                'coingecko_id': 'binancecoin'
            },
            'polygon': {
                'rpc': 'https://polygon-rpc.com',
                'native': 'MATIC',
                'decimals': 18,
                'coingecko_id': 'matic-network'
            },
            'arbitrum': {
                'rpc': 'https://arb1.arbitrum.io/rpc',
                'native': 'ETH',
                'decimals': 18,
                'coingecko_id': 'ethereum'
            },
            'optimism': {
                'rpc': 'https://mainnet.optimism.io',
                'native': 'ETH',
                'decimals': 18,
                'coingecko_id': 'ethereum'
            },
            'base': {
                'rpc': 'https://mainnet.base.org',
                'native': 'ETH',
                'decimals': 18,
                'coingecko_id': 'ethereum'
            },
            'avalanche': {
                'rpc': 'https://api.avax.network/ext/bc/C/rpc',
                'native': 'AVAX',
                'decimals': 18,
                'coingecko_id': 'avalanche-2'
            }
        }
        
        # Fetch USD prices from CoinGecko
        unique_coingecko_ids = set(cfg['coingecko_id'] for cfg in chain_config.values())
        prices = {}
        try:
            price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(unique_coingecko_ids)}&vs_currencies=usd"
            price_response = requests.get(price_url, timeout=5)
            if price_response.ok:
                price_data = price_response.json()
                for gecko_id, data in price_data.items():
                    prices[gecko_id] = data.get('usd', 0)
        except Exception as e:
            print(f"Error fetching prices: {e}")
        
        balances = []
        total_usd = 0
        
        for chain in chain_list:
            if chain not in chain_config:
                continue
                
            config = chain_config[chain]
            
            try:
                # Fetch native token balance via eth_getBalance
                response = requests.post(
                    config['rpc'],
                    json={
                        'jsonrpc': '2.0',
                        'method': 'eth_getBalance',
                        'params': [address, 'latest'],
                        'id': 1
                    },
                    timeout=10
                )
                
                if response.ok:
                    result = response.json().get('result', '0x0')
                    balance_wei = int(result, 16)
                    balance = balance_wei / (10 ** config['decimals'])
                    
                    usd_price = prices.get(config['coingecko_id'], 0)
                    balance_usd = balance * usd_price
                    total_usd += balance_usd
                    
                    if balance > 0:  # Only include chains with balance
                        balances.append({
                            'chain': chain.capitalize(),
                            'token': config['native'],
                            'balance': balance,
                            'balance_usd': balance_usd,
                            'price_usd': usd_price
                        })
            except Exception as e:
                print(f"Error fetching {chain} balance: {e}")
                continue
        
        return {
            'address': address,
            'chains_checked': chain_list,
            'balances': balances,
            'total_usd': total_usd,
            'timestamp': _dt.datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch wallet balance: {str(e)}")


# Background task to update APY history and check alerts
async def _update_vault_apy_monitor():
    """Background task that fetches vault data periodically and checks for alert conditions."""
    while True:
        try:
            # Fetch current vault data
            vault_data = get_defi_vaults()
            vaults = vault_data.get('vaults', [])
            
            current_time = time.time()
            timestamp_iso = _dt.datetime.utcnow().isoformat()
            
            for vault in vaults:
                pool_id = vault['id']
                apy = vault.get('apy')
                apy_base = vault.get('apy_base')
                
                # Store in history
                if pool_id not in _vault_apy_history:
                    _vault_apy_history[pool_id] = []
                
                _vault_apy_history[pool_id].append({
                    'timestamp': current_time,
                    'timestamp_iso': timestamp_iso,
                    'apy': apy,
                    'apy_base': apy_base,
                    'apy_reward': vault.get('apy_reward'),
                    'tvl_usd': vault.get('tvl_usd'),
                    'outlier': vault.get('outlier', False)
                })
                
                # Keep only last 7 days of history
                cutoff = current_time - (7 * 24 * 3600)
                _vault_apy_history[pool_id] = [
                    h for h in _vault_apy_history[pool_id] if h['timestamp'] >= cutoff
                ]
                
                # Check alerts for this vault
                await _check_vault_alerts(pool_id, vault)
            
            print(f"[APY Monitor] Updated {len(vaults)} vaults, stored history")
            
        except Exception as e:
            print(f"[APY Monitor] Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Update every 5 minutes
        await asyncio.sleep(300)


async def _check_vault_alerts(pool_id: str, current_vault: dict):
    """Check if any alerts should be triggered for this vault."""
    current_apy = current_vault.get('apy')
    if current_apy is None:
        return
    
    # Get historical data for comparison
    history = _vault_apy_history.get(pool_id, [])
    if len(history) < 2:
        return  # Need at least 2 data points to compare
    
    previous = history[-2]  # Previous data point
    previous_apy = previous.get('apy')
    
    # Check each alert configured for this pool
    for alert_id, alert in _vault_alerts.items():
        if not alert.get('active') or alert['pool_id'] != pool_id:
            continue
        
        alert_type = alert['alert_type']
        threshold = alert['threshold']
        should_trigger = False
        message = ""
        
        if alert_type == 'apy_drop':
            # Alert if APY drops by threshold percentage
            if previous_apy and previous_apy > 0:
                pct_change = ((current_apy - previous_apy) / previous_apy) * 100
                if pct_change <= -threshold:
                    should_trigger = True
                    message = f"APY dropped {abs(pct_change):.1f}% (from {previous_apy:.2f}% to {current_apy:.2f}%)"
        
        elif alert_type == 'apy_spike':
            # Alert if APY increases by threshold percentage
            if previous_apy and previous_apy > 0:
                pct_change = ((current_apy - previous_apy) / previous_apy) * 100
                if pct_change >= threshold:
                    should_trigger = True
                    message = f"APY spiked {pct_change:.1f}% (from {previous_apy:.2f}% to {current_apy:.2f}%)"
        
        elif alert_type == 'apy_below':
            # Alert if APY falls below absolute threshold
            if current_apy < threshold:
                should_trigger = True
                message = f"APY fell below {threshold}% (current: {current_apy:.2f}%)"
        
        elif alert_type == 'apy_above':
            # Alert if APY rises above absolute threshold
            if current_apy > threshold:
                should_trigger = True
                message = f"APY rose above {threshold}% (current: {current_apy:.2f}%)"
        
        if should_trigger:
            await _trigger_alert(alert, current_vault, message)


async def _trigger_alert(alert: dict, vault: dict, message: str):
    """Trigger an alert notification."""
    alert_id = alert['alert_id']
    
    # Avoid duplicate alerts (minimum 15 minutes between triggers)
    last_triggered = alert.get('last_triggered', 0)
    if time.time() - last_triggered < 900:  # 15 minutes
        return
    
    alert['last_triggered'] = time.time()
    alert['trigger_count'] = alert.get('trigger_count', 0) + 1
    
    notification_data = {
        'alert_id': alert_id,
        'pool_id': vault['id'],
        'vault_name': vault['name'],
        'protocol': vault['protocol'],
        'chain': vault['chain'],
        'current_apy': vault['apy'],
        'message': message,
        'timestamp': _dt.datetime.utcnow().isoformat(),
        'defillama_url': vault.get('defillama_url'),
        'vault_url': vault.get('vault_url')
    }
    
    print(f"[ALERT] {message} - {vault['name']}")
    
    # Send webhook notification if configured
    if alert.get('notification_method') == 'webhook' and alert.get('webhook_url'):
        try:
            import json
            req = _urllib_request.Request(
                alert['webhook_url'],
                data=json.dumps(notification_data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with _urllib_request.urlopen(req, timeout=5) as resp:
                print(f"[ALERT] Webhook sent successfully to {alert['webhook_url']}")
        except Exception as e:
            print(f"[ALERT] Failed to send webhook: {e}")
    
    # TODO: Add email notification support
    # TODO: Broadcast to WebSocket clients monitoring this vault


@app.post('/api/live-strategy/start')
async def api_live_strategy_start(req: Request):
    """Start the live strategy for a given symbol. Body: { symbol: 'ALPINEUSDT', mode: 'bear' }

    Returns the start status. Execution defaults to paper unless ARB_ALLOW_LIVE_EXECUTION=1 and proper auth is provided.
    Supports multiple concurrent strategies on different symbols.
    """
    body = await req.json()
    symbol = (body.get('symbol') or '').strip()
    mode = (body.get('mode') or 'bear').strip()
    interval = (body.get('interval') or '1m').strip()
    
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol required')
    
    try:
        from .live_strategy import LiveStrategy
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'live_strategy unavailable: {e}')
    
    global _live_strategy_instances
    
    # Check if strategy already running for this symbol
    if symbol in _live_strategy_instances and _live_strategy_instances[symbol].running():
        return {'started': False, 'reason': f'strategy already running for {symbol}', 'symbol': symbol}
    
    # Create and start new strategy instance
    inst = LiveStrategy(symbol, mode=mode, interval=interval)
    started = inst.start()
    
    if not started:
        raise HTTPException(status_code=500, detail='failed-to-start')
    
    _live_strategy_instances[symbol] = inst
    
    return {
        'started': True, 
        'symbol': symbol, 
        'mode': mode,
        'interval': interval,
        'active_strategies': len(_live_strategy_instances),
        'all_strategies': list(_live_strategy_instances.keys())
    }


@app.post('/api/live-strategy/stop')
async def api_live_strategy_stop(req: Request = None):
    """Stop strategy for a specific symbol or all strategies if no symbol provided.
    
    Body (optional): { symbol: 'BTCUSDT' }
    If no symbol provided, stops all strategies.
    """
    global _live_strategy_instances
    
    symbol = None
    if req:
        try:
            body = await req.json()
            symbol = (body.get('symbol') or '').strip() if body else None
        except Exception:
            pass
    
    stopped_strategies = []
    
    if symbol:
        # Stop specific strategy
        if symbol not in _live_strategy_instances:
            return {'stopped': False, 'reason': f'no strategy running for {symbol}', 'symbol': symbol}
        
        try:
            await _live_strategy_instances[symbol].stop()
        except Exception as e:
            print(f"Error stopping strategy for {symbol}: {e}")
        
        del _live_strategy_instances[symbol]
        stopped_strategies.append(symbol)
        
        return {
            'stopped': True, 
            'symbol': symbol,
            'remaining_strategies': len(_live_strategy_instances),
            'active_symbols': list(_live_strategy_instances.keys())
        }
    else:
        # Stop all strategies
        if not _live_strategy_instances:
            return {'stopped': False, 'reason': 'no strategies running'}
        
        for sym, inst in list(_live_strategy_instances.items()):
            try:
                await inst.stop()
                stopped_strategies.append(sym)
            except Exception as e:
                print(f"Error stopping strategy for {sym}: {e}")
        
        _live_strategy_instances.clear()
        
        return {
            'stopped': True,
            'stopped_strategies': stopped_strategies,
            'count': len(stopped_strategies)
        }


@app.get('/api/live-strategy/status')
async def api_live_strategy_status(symbol: str = None):
    """Get status of live strategies.
    
    If symbol provided: returns status for that specific strategy
    If no symbol: returns status for all running strategies
    """
    global _live_strategy_instances
    
    if symbol:
        # Get status for specific symbol
        if symbol not in _live_strategy_instances:
            return {'running': False, 'symbol': symbol}
        
        inst = _live_strategy_instances[symbol]
        return {
            'running': inst.running(),
            'symbol': inst.symbol,
            'mode': inst.mode,
            'interval': getattr(inst, 'interval', '1m')
        }
    else:
        # Get status for all strategies
        if not _live_strategy_instances:
            return {
                'running': False,
                'active_count': 0,
                'strategies': []
            }
        
        strategies = []
        for sym, inst in _live_strategy_instances.items():
            strategies.append({
                'symbol': sym,
                'mode': inst.mode,
                'interval': getattr(inst, 'interval', '1m'),
                'running': inst.running()
            })
        
        return {
            'running': True,
            'active_count': len(strategies),
            'strategies': strategies
        }


@app.get('/api/live-check')
async def api_live_check(symbol: str = 'ALPINEUSDT'):
    """Perform safe, read-only checks against the configured Binance credentials.

    Returns a JSON object summarizing whether keys are present and whether we can
    read balances, markets, and positions. Does NOT place orders.
    """
    out: dict = {}
    key = (os.environ.get('BINANCE_API_KEY') or '').strip()
    secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
    out['has_key'] = bool(key)
    out['has_secret'] = bool(secret)

    # Attempt to instantiate a CCXTExchange via the cached helper (non-blocking)
    try:
        inst = await _get_ccxt_instance('binance', key if key else None, secret if secret else None)
        if inst is None:
            out['inst_ok'] = False
            out['inst_error'] = 'ccxt instance unavailable'
            return out
        out['inst_ok'] = True

        # fetch balance (safe, read-only)
        try:
            bal = await asyncio.to_thread(lambda: getattr(inst, 'client').fetch_balance())
            out['fetch_balance_succeeds'] = True
            total = bal.get('total') if isinstance(bal, dict) else None
            if isinstance(total, dict):
                out['usdt_total'] = total.get('USDT') or total.get('usdt') or None
            else:
                out['balance_shape'] = type(bal).__name__
        except Exception as e:
            out['fetch_balance_succeeds'] = False
            out['fetch_balance_error'] = str(e)

        # load markets and check symbol presence
        try:
            mk = await asyncio.to_thread(lambda: getattr(inst, 'client').load_markets())
            out['load_markets_succeeds'] = True
            try:
                # Build a small set of likely symbol variants to handle exchange naming
                def _symbol_variants(sym: str):
                    s = (sym or '').upper()
                    variants = set()
                    if not s:
                        return variants
                    variants.add(s)
                    variants.add(s.replace('/', ''))
                    variants.add(s.replace('-', ''))

                    # If user supplied a base like 'XPLUS' or 'XPLUSDT', try adding common quote tokens
                    if not any(q in s for q in ['USDT', 'USD', ':', '.P', 'PERP']):
                        variants.add(s + 'USDT')
                        variants.add(s + ':USDT')
                        variants.add(s + 'USDT.P')
                        variants.add(s + 'USDT_PERP')

                    # If symbol already ends with USDT, also include base-only variant
                    if s.endswith('USDT'):
                        base = s[:-4]
                        variants.add(base)

                    # Common CCXT/Binance futures suffixes
                    variants.add(s + '.P')
                    variants.add(s + ':USDT')
                    variants.add(s.replace('USDT', '') + 'USDT.P' if 'USDT' in s else s + 'USDT.P')

                    # Return normalized set
                    return {v for v in variants if v}

                mk_keys = set(mk.keys())
                # direct membership or any variant match
                present = False
                try:
                    for v in _symbol_variants(symbol):
                        if v in mk_keys:
                            present = True
                            break
                    # fallback: substring-insensitive match against market keys
                    if not present:
                        up = (symbol or '').upper()
                        for k in mk_keys:
                            ku = str(k).upper()
                            if up and (up in ku or up.replace('/', '') in ku):
                                present = True
                                break
                except Exception:
                    present = False
                out['symbol_present'] = present
                # If not present in loaded markets, try Binance Futures REST ticker lookup
                if not out['symbol_present'] and symbol:
                    try:
                        import urllib.request as _urlreq, urllib.parse as _urlparse, ssl as _ssl
                        cand = []
                        s = symbol.replace('/', '').upper()
                        cand.append(s)
                        # add common futures/perp suffix forms
                        if not s.endswith('.P'):
                            cand.append(s + '.P')
                        if not s.endswith('USDT'):
                            cand.append(s + 'USDT')
                            cand.append(s + 'USDT.P')
                        cand = list(dict.fromkeys(cand))
                        checked = []
                        ctx = _ssl.create_default_context()
                        for c in cand:
                            try:
                                qs = _urlparse.urlencode({'symbol': c})
                                url = BINANCE_FUTURES_TICKER_URL + '?' + qs
                                with _urlreq.urlopen(url, context=ctx, timeout=5) as resp:
                                    txt = resp.read().decode('utf8')
                                    try:
                                        j = json.loads(txt)
                                    except Exception:
                                        j = None
                                    checked.append({'symbol': c, 'resp': j})
                                    # typical response: { 'symbol': 'XPLUSUSDT.P', 'price': '0.123' } or list
                                    if isinstance(j, dict) and (j.get('symbol') or j.get('price')):
                                        out['symbol_present'] = True
                                        out['checked_futures_ticker'] = c
                                        break
                            except Exception:
                                continue
                        if 'checked_futures_ticker' not in out:
                            out['checked_futures_sample'] = checked[:3]
                    except Exception:
                        pass
                # As a last resort, try creating a CCXT instance configured for
                # USDT-M futures (defaultType='future') and inspect its markets.
                if not out.get('symbol_present'):
                    try:
                        from .exchanges.ccxt_adapter import CCXTExchange
                        # construct a futures-configured exchange in a thread
                        fut_inst = await asyncio.to_thread(
                            lambda: CCXTExchange(
                                'binance',
                                key if key else None,
                                secret if secret else None,
                                options={'defaultType': 'future'},
                            )
                        )
                        try:
                            fut_mk = await asyncio.to_thread(lambda: getattr(fut_inst.client).load_markets())
                            try:
                                if (symbol in fut_mk) or (symbol.replace('/', '') in fut_mk) or any(symbol in str(k) for k in fut_mk):
                                    out['symbol_present'] = True
                                    out['futures_markets_checked'] = True
                                    out['futures_market_keys_sample'] = list(list(fut_mk.keys())[:10])
                            except Exception:
                                pass
                        except Exception as e:
                            out['futures_load_markets_error'] = str(e)
                    except Exception as e:
                        out['futures_check_error'] = str(e)
            except Exception:
                pass
            # sample a few market keys for debugging
            try:
                out['market_keys_sample'] = list(list(mk.keys())[:10])
            except Exception:
                out['market_keys_sample'] = []
        except Exception as e:
            out['load_markets_succeeds'] = False
            out['load_markets_error'] = str(e)

        # fetch positions (if supported)
        try:
            client = getattr(inst, 'client')
            if hasattr(client, 'fetch_positions'):
                ps = await asyncio.to_thread(lambda: client.fetch_positions())
                out['fetch_positions_succeeds'] = True
                out['positions_count'] = len(ps) if isinstance(ps, (list, tuple)) else None
            else:
                out['fetch_positions_succeeds'] = False
                out['fetch_positions_msg'] = 'method not available'
        except Exception as e:
            out['fetch_positions_succeeds'] = False
            out['fetch_positions_error'] = str(e)

    except Exception as e:
        out['inst_ok'] = False
        out['inst_error'] = str(e)

    return out

@app.get('/api/account-info')
async def api_account_info():
    """Get Binance Futures account information (balance, positions, permissions)."""
    key = (os.environ.get('BINANCE_API_KEY') or '').strip()
    secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
    
    if not key or not secret:
        raise HTTPException(status_code=400, detail='BINANCE_API_KEY and BINANCE_API_SECRET required')
    
    try:
        from .exchanges.ccxt_adapter import CCXTExchange
        
        inst = await asyncio.to_thread(
            lambda: CCXTExchange(
                'binance',
                api_key=key,
                secret=secret,
                options={'defaultType': 'future'}
            )
        )
        
        out = {}
        
        # Fetch balance
        def _balance():
            return inst.client.fetch_balance()
        balance = await asyncio.to_thread(_balance)
        out['balance'] = {
            'USDT': balance.get('USDT', {}).get('total', 0) if 'USDT' in balance else 0,
            'total_wallet_balance': balance.get('info', {}).get('totalWalletBalance')
        }
        
        # Fetch positions
        def _positions():
            return inst.client.fetch_positions()
        positions = await asyncio.to_thread(_positions)
        open_positions = [p for p in positions if p.get('contracts', 0) != 0]
        out['positions'] = {
            'total': len(positions),
            'open': len(open_positions),
            'details': [
                {
                    'symbol': p.get('symbol'),
                    'side': p.get('side'),
                    'contracts': p.get('contracts'),
                    'notional': p.get('notional'),
                    'unrealized_pnl': p.get('unrealizedPnl')
                }
                for p in open_positions[:10]  # Limit to 10 for display
            ]
        }
        
        # Try to fetch open orders (read-only, should work with current permissions)
        def _orders():
            return inst.client.fetch_open_orders('BTC/USDT')
        try:
            orders = await asyncio.to_thread(_orders)
            out['can_read_orders'] = True
            out['open_orders_count'] = len(orders)
        except Exception as e:
            out['can_read_orders'] = False
            out['read_orders_error'] = str(e)
        
        return out
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to fetch account info: {str(e)}')

@app.post('/api/test-order')
async def api_test_order(req: Request):
    """Test placing an order on Binance Futures (uses testnet if available, otherwise paper trade).
    
    Request body: {
        "symbol": "BTCUSDT",
        "side": "buy" | "sell",
        "amount": 0.001,
        "test_mode": true  # if false, will attempt real order (requires ARB_ALLOW_LIVE_ORDERS=1)
    }
    
    Returns order details or error.
    """
    body = await req.json()
    symbol = (body.get('symbol') or '').strip()
    side = (body.get('side') or '').strip().lower()
    amount = body.get('amount')
    test_mode = body.get('test_mode', True)
    
    if not symbol or not side or not amount:
        raise HTTPException(status_code=400, detail='symbol, side, and amount required')
    
    if side not in ['buy', 'sell']:
        raise HTTPException(status_code=400, detail='side must be buy or sell')
    
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError('amount must be positive')
    except Exception:
        raise HTTPException(status_code=400, detail='invalid amount')
    
    # Check if live orders are allowed
    if not test_mode:
        allow_live = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        if not allow_live:
            raise HTTPException(status_code=403, detail='live orders disabled. Set ARB_ALLOW_LIVE_ORDERS=1 to enable')
    
    out = {}
    key = (os.environ.get('BINANCE_API_KEY') or '').strip()
    secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
    
    if not key or not secret:
        raise HTTPException(status_code=400, detail='BINANCE_API_KEY and BINANCE_API_SECRET required')
    
    try:
        from .exchanges.ccxt_adapter import CCXTExchange
        
        # Create futures instance
        inst = await asyncio.to_thread(
            lambda: CCXTExchange(
                'binance',
                api_key=key,
                secret=secret,
                options={'defaultType': 'future'}
            )
        )
        
        if test_mode:
            # Use Binance test order endpoint (validates but doesn't execute)
            def _test_order():
                # Create test order using Binance's test endpoint
                # This validates the order but doesn't place it
                params = {'test': True}
                return inst.client.create_order(symbol, 'market', side, amount, None, params)
            
            try:
                test_result = await asyncio.to_thread(_test_order)
                out['mode'] = 'test'
                out['symbol'] = symbol
                out['side'] = side
                out['amount'] = amount
                out['test_result'] = str(test_result) if test_result else 'validated'
                out['message'] = 'Test order validated successfully (no real order placed)'
                out['success'] = True
            except Exception as e:
                # If test order fails, it means the order would fail in live mode too
                raise HTTPException(status_code=400, detail=f'Test order validation failed: {str(e)}')
        else:
            # Attempt real order
            def _place():
                return inst.place_order(symbol, side, amount)
            
            order_id = await asyncio.to_thread(_place)
            out['mode'] = 'live'
            out['symbol'] = symbol
            out['side'] = side
            out['amount'] = amount
            out['order_id'] = order_id
            out['success'] = True
            out['message'] = 'Order placed successfully'
            
        return out
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Order failed: {str(e)}')

@app.get('/api/dashboard')
async def api_dashboard(mode: str = 'test'):
    """Get live trading dashboard data (positions, signals, trades, statistics).
    
    Args:
        mode: 'live' to fetch real Binance balance, 'test' for simulated balance
    """
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        
        # Update P&L for all open positions with current prices
        positions = dashboard.get_all_positions()
        
        # Filter positions based on mode
        if mode == 'live':
            # Only show live positions in live mode
            positions = [p for p in positions if getattr(p, 'is_live', False)]
            
            # Reconcile with Binance - check if positions still exist
            live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
            if live_enabled and positions:
                try:
                    # Fetch actual positions from Binance
                    binance_positions = await asyncio.to_thread(_get_binance_positions)
                    binance_symbols = {p['symbol'] for p in binance_positions if p['positionAmt'] != 0}
                    
                    # Check each local position
                    positions_to_close = []
                    for pos in positions:
                        if pos.symbol not in binance_symbols:
                            print(f"[RECONCILE] Position {pos.symbol} not found on Binance - marking as closed")
                            positions_to_close.append(pos)
                    
                    # Close positions that don't exist on Binance anymore
                    for pos in positions_to_close:
                        # Fetch last known price to calculate final PNL
                        current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, pos.market if hasattr(pos, 'market') else 'futures')
                        if current_price:
                            dashboard.close_position(pos.symbol, current_price, reason='stop_loss')
                            print(f"[RECONCILE] Closed {pos.symbol} @ ${current_price:.2f}")
                        positions.remove(pos)
                    
                except Exception as e:
                    print(f"[WARNING] Failed to reconcile positions with Binance: {e}")
        else:
            # Only show test positions in test mode
            positions = [p for p in positions if not getattr(p, 'is_live', False)]
        
        # Update PNL for filtered positions
        for pos in positions:
            try:
                # Fetch current price from the correct market (spot or futures)
                market = getattr(pos, 'market', None)
                
                if market is None:
                    # Try futures first (most manual trades use leverage)
                    current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'futures')
                    if not current_price:
                        current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'spot')
                else:
                    current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, market)
                
                if current_price:
                    pos.update_pnl(current_price)
                else:
                    print(f"[WARNING] Could not fetch price for {pos.symbol}")
            except Exception as e:
                print(f"[ERROR] Failed to update P&L for {pos.symbol}: {e}")
        
        # Get dashboard state
        state = dashboard.get_full_state()
        
        # Override positions in state with filtered positions
        state['positions'] = [
            {
                'symbol': p.symbol,
                'side': p.side,
                'entry_price': p.entry_price,
                'size': p.size,
                'entry_time': p.entry_time,
                'stop_loss': p.stop_loss,
                'take_profit': p.take_profit,
                'unrealized_pnl': p.unrealized_pnl,
                'unrealized_pnl_pct': p.unrealized_pnl_pct,
            }
            for p in positions
        ]
        
        # Recalculate statistics based on filtered positions
        state['statistics']['active_positions'] = len(positions)
        state['statistics']['unrealized_pnl'] = sum(p.unrealized_pnl for p in positions)
        
        # Check if we should show live balance instead of test balance
        # Only fetch live balance if mode='live' AND ARB_ALLOW_LIVE_ORDERS is enabled
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        
        if mode == 'live' and live_enabled:
            try:
                # Fetch live Binance balance
                balance_info = await asyncio.to_thread(_get_binance_futures_balance)
                
                if balance_info.get('success'):
                    # Get wallet balance (without unrealized P&L) and unrealized P&L from Binance
                    total_balance = balance_info.get('balance', 0.0)  # Total (with unrealized P&L)
                    wallet_balance = balance_info.get('wallet_balance', total_balance)  # Wallet (without unrealized P&L)
                    unrealized_pnl_binance = balance_info.get('unrealized_pnl', 0.0)  # From Binance positions
                    
                    # Replace test balance with live balance
                    state['balance'] = {
                        'current': total_balance,  # Total balance (wallet + unrealized P&L)
                        'initial': wallet_balance,  # Wallet balance (without unrealized P&L)
                        'pnl': unrealized_pnl_binance,  # Use Binance's unrealized P&L
                        'pnl_pct': (unrealized_pnl_binance / wallet_balance * 100) if wallet_balance > 0 else 0.0,
                        'live': True,  # Flag to indicate this is live balance
                        'wallet_balance': wallet_balance,  # Wallet balance for display
                        'unrealized_pnl': unrealized_pnl_binance,  # Unrealized P&L from Binance
                        'realized_pnl': 0.0,  # Realized P&L is already in wallet_balance
                        'total_fees_paid': 0.0  # Fees are already deducted from wallet_balance
                    }
            except Exception as e:
                print(f"[WARNING] Failed to fetch live balance, using test balance: {e}")
        else:
            # Test mode - ensure we're showing test balance with test positions only
            test_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
            test_balance = state['balance']['current']
            
            # Recalculate balance including unrealized PNL from test positions
            state['balance'] = {
                'current': test_balance + test_unrealized_pnl,
                'initial': state['balance']['initial'],
                'pnl': test_unrealized_pnl + (test_balance - state['balance']['initial']),
                'pnl_pct': ((test_unrealized_pnl + (test_balance - state['balance']['initial'])) / state['balance']['initial'] * 100) if state['balance']['initial'] > 0 else 0.0,
                'live': False,  # Flag to indicate this is test balance
                'unrealized_pnl': test_unrealized_pnl
            }
        
        return state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get dashboard: {str(e)}')

@app.get('/api/dashboard/positions')
async def api_dashboard_positions():
    """Get all active positions."""
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        positions = dashboard.get_all_positions()
        
        # Update P&L for all positions with current prices
        for pos in positions:
            try:
                # Fetch current price from the correct market (spot or futures)
                market = getattr(pos, 'market', None)
                
                if market is None:
                    # Try futures first, then spot
                    current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'futures')
                    if not current_price:
                        current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'spot')
                else:
                    current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, market)
                
                if current_price:
                    pos.update_pnl(current_price)
            except Exception as e:
                print(f"[ERROR] Failed to update P&L for {pos.symbol}: {e}")
        
        return {'positions': [vars(p) for p in positions]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get positions: {str(e)}')

@app.get('/api/dashboard/signals')
async def api_dashboard_signals(limit: int = 20):
    """Get recent trading signals."""
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        signals = dashboard.get_recent_signals(limit)
        return {'signals': [vars(s) for s in signals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get signals: {str(e)}')

@app.get('/api/dashboard/trades')
async def api_dashboard_trades(limit: int = 20):
    """Get recent completed trades."""
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        trades = dashboard.get_recent_trades(limit)
        return {'trades': [vars(t) for t in trades]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get trades: {str(e)}')

@app.get('/api/dashboard/statistics')
async def api_dashboard_statistics():
    """Get trading statistics."""
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        return dashboard.get_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get statistics: {str(e)}')

@app.post('/api/dashboard/reset')
async def api_dashboard_reset():
    """Reset dashboard data (for testing)."""
    try:
        from .live_dashboard import get_dashboard
        dashboard = get_dashboard()
        dashboard.reset()
        return {'success': True, 'message': 'Dashboard reset successfully'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to reset dashboard: {str(e)}')

@app.get('/api/binance/balance')
async def api_binance_balance():
    """Get comprehensive Binance Futures balance including fees and PNL."""
    try:
        from .live_dashboard import get_dashboard
        
        dashboard = get_dashboard()
        
        # Get raw Binance Futures balance
        balance_info = await asyncio.to_thread(_get_binance_futures_balance)
        
        if not balance_info.get('success'):
            return balance_info
        
        # Get balances from Binance
        total_balance = balance_info.get('balance', 0.0)  # Total (with unrealized P&L)
        wallet_balance = balance_info.get('wallet_balance', total_balance)  # Wallet (without unrealized P&L)
        unrealized_pnl_binance = balance_info.get('unrealized_pnl', 0.0)  # From Binance
        available = balance_info.get('available', 0.0)
        used = balance_info.get('used', 0.0)
        
        # Calculate net balance with fees (using wallet balance as base)
        net_info = dashboard.calculate_net_balance(wallet_balance)
        
        return {
            'success': True,
            'wallet_balance': wallet_balance,  # Actual wallet balance (207.35)
            'available': available,
            'used': used,
            'unrealized_pnl': unrealized_pnl_binance,  # Use Binance's unrealized P&L (-33.22)
            'realized_pnl': net_info['realized_pnl'],
            'total_fees_paid': net_info['total_fees_paid'],
            'net_balance': total_balance,  # Total balance after P&L (174.13)
            'balance': available,  # Available balance for trading
            'currency': 'USDT'
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch Binance balance: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to fetch balance: {str(e)}')

@app.get('/api/binance/order-history')
async def api_binance_order_history(
    symbol: Optional[str] = None,
    limit: int = 100,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None
):
    """
    Get order history from Binance Futures.
    
    Args:
        symbol: Trading pair symbol (e.g., 'MYXUSDT'). If None, gets all symbols.
        limit: Maximum number of orders to return (default 100, max 1000)
        start_time: Filter by start timestamp in milliseconds
        end_time: Filter by end timestamp in milliseconds
    """
    try:
        # Fetch orders from Binance
        orders = await asyncio.to_thread(
            _get_binance_order_history,
            symbol=symbol,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
        
        if not orders.get('success'):
            raise HTTPException(status_code=500, detail=orders.get('error', 'Failed to fetch orders'))
        
        return {
            'success': True,
            'orders': orders.get('orders', []),
            'count': len(orders.get('orders', [])),
            'symbol': symbol,
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch order history: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to fetch order history: {str(e)}')

def _get_binance_order_history(symbol: Optional[str] = None, limit: int = 100, start_time: Optional[int] = None, end_time: Optional[int] = None):
    """Synchronous function to get Binance Futures order history."""
    try:
        import ccxt
        
        # Get API keys from environment
        api_key = os.environ.get('BINANCE_API_KEY', '')
        api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        if not api_key or not api_secret:
            return {
                'success': False,
                'error': 'Binance API keys not configured',
                'orders': []
            }
        
        # Initialize Binance Futures exchange
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'future',
            }
        })
        
        # Build params for Binance Futures API
        params = {}
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        # Fetch orders
        orders = []
        
        if symbol:
            # Convert symbol to CCXT format (e.g., MYXUSDT -> MYX/USDT:USDT)
            if '/' not in symbol:
                # Assume it's a normalized symbol like MYXUSDT
                base = symbol[:-4]  # Remove USDT
                quote = symbol[-4:]  # Get USDT
                ccxt_symbol = f"{base}/{quote}:{quote}"
            else:
                ccxt_symbol = symbol
            
            # For Binance Futures, use fetch_closed_orders or fetch_orders with symbol
            try:
                # Try closed orders first (filled/canceled orders)
                orders = exchange.fetch_closed_orders(ccxt_symbol, limit=limit, params=params)
            except:
                # Fallback to all orders
                orders = exchange.fetch_orders(ccxt_symbol, limit=limit, params=params)
        else:
            # Fetch all orders across all symbols
            # Binance Futures doesn't support fetch_orders without symbol
            # So we need to use the direct API call
            try:
                # Use fapiPrivateGetAllOrders for all orders
                params['limit'] = limit
                raw_orders = exchange.fapiPrivateGetAllOrders(params)
                
                # Convert raw orders to CCXT format
                for raw_order in raw_orders:
                    try:
                        parsed = exchange.parse_order(raw_order)
                        orders.append(parsed)
                    except:
                        pass
            except Exception as e:
                print(f"[DEBUG] Failed to fetch all orders, trying recent trades: {e}")
                # Alternative: Get recent filled orders via trades
                try:
                    my_trades = exchange.fetch_my_trades(limit=limit, params=params)
                    # Group trades by order ID to create order-like objects
                    order_map = {}
                    for trade in my_trades:
                        order_id = trade.get('order')
                        if order_id not in order_map:
                            order_map[order_id] = {
                                'id': order_id,
                                'symbol': trade.get('symbol'),
                                'side': trade.get('side'),
                                'type': trade.get('type', 'market'),
                                'status': 'closed',
                                'price': trade.get('price'),
                                'average': trade.get('price'),
                                'amount': trade.get('amount', 0),
                                'filled': trade.get('amount', 0),
                                'cost': trade.get('cost', 0),
                                'fee': trade.get('fee'),
                                'timestamp': trade.get('timestamp'),
                                'datetime': trade.get('datetime'),
                            }
                        else:
                            # Aggregate multiple fills for same order
                            order_map[order_id]['amount'] += trade.get('amount', 0)
                            order_map[order_id]['filled'] += trade.get('amount', 0)
                            order_map[order_id]['cost'] += trade.get('cost', 0)
                    
                    orders = list(order_map.values())
                except Exception as e2:
                    print(f"[DEBUG] Failed to fetch trades: {e2}")
                    orders = []
        
        # Format orders for frontend
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'id': order.get('id'),
                'client_order_id': order.get('clientOrderId'),
                'symbol': order.get('symbol'),
                'type': order.get('type'),
                'side': order.get('side'),
                'status': order.get('status'),
                'price': order.get('price'),
                'average': order.get('average'),
                'amount': order.get('amount'),
                'filled': order.get('filled'),
                'remaining': order.get('remaining'),
                'cost': order.get('cost'),
                'fee': order.get('fee'),
                'timestamp': order.get('timestamp'),
                'datetime': order.get('datetime'),
                'reduce_only': order.get('reduceOnly'),
                'post_only': order.get('postOnly'),
                'time_in_force': order.get('timeInForce'),
            })
        
        return {
            'success': True,
            'orders': formatted_orders
        }
        
    except Exception as e:
        print(f"[ERROR] Binance order history fetch error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'orders': []
        }

def _get_binance_futures_balance():
    """Synchronous function to get Binance Futures balance."""
    try:
        import ccxt
        
        # Get API keys from environment
        api_key = os.environ.get('BINANCE_API_KEY', '')
        api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        if not api_key or not api_secret:
            return {
                'success': False,
                'error': 'Binance API keys not configured',
                'balance': 0.0,
                'available': 0.0
            }
        
        # Initialize Binance Futures exchange
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'future',  # Use futures
            }
        })
        
        # Fetch balance
        balance = exchange.fetch_balance()
        
        # Get USDT balance
        usdt_balance = balance.get('USDT', {})
        total = usdt_balance.get('total', 0.0)  # This includes unrealized P&L
        free = usdt_balance.get('free', 0.0)
        used = usdt_balance.get('used', 0.0)
        
        # Get wallet balance (without unrealized PNL) from info
        # In Binance Futures: walletBalance = actual deposited balance
        # totalWalletBalance = walletBalance + unrealizedProfit
        wallet_balance = total  # Default to total
        unrealized_pnl = 0.0
        
        # Try to get the actual wallet balance from the raw info
        info = balance.get('info', {})
        if isinstance(info, dict):
            assets = info.get('assets', [])
            for asset in assets:
                if asset.get('asset') == 'USDT':
                    # walletBalance is the actual balance without unrealized P&L
                    wallet_balance = float(asset.get('walletBalance', total))
                    unrealized_pnl = float(asset.get('unrealizedProfit', 0.0))
                    break
        
        return {
            'success': True,
            'balance': total,  # Total balance (with unrealized P&L)
            'wallet_balance': wallet_balance,  # Wallet balance (without unrealized P&L)
            'unrealized_pnl': unrealized_pnl,  # Unrealized P&L from Binance
            'available': free,
            'used': used,
            'currency': 'USDT'
        }
        
    except Exception as e:
        print(f"[ERROR] Binance balance fetch error: {e}")
        return {
            'success': False,
            'error': str(e),
            'balance': 0.0,
            'available': 0.0
        }

def _get_binance_positions():
    """Synchronous function to get Binance Futures positions."""
    try:
        import ccxt
        
        # Get API keys from environment
        api_key = os.environ.get('BINANCE_API_KEY', '')
        api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        if not api_key or not api_secret:
            return []
        
        # Initialize Binance Futures exchange
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'future',
            }
        })
        
        # Fetch positions
        positions = exchange.fetch_positions()
        
        # Filter to only positions with non-zero amount
        active_positions = [p for p in positions if float(p.get('contracts', 0)) != 0]
        
        print(f"[BINANCE] Found {len(active_positions)} active positions on Binance")
        for p in active_positions:
            print(f"[BINANCE] - {p['symbol']}: {p['contracts']} contracts, side={p['side']}")
        
        return positions
        
    except Exception as e:
        print(f"[ERROR] Binance positions fetch error: {e}")
        return []

@app.post('/api/manual-trade')
async def api_manual_trade(request: dict):
    """Place a manual test trade (paper trading).
    
    Body:
    {
        "symbol": "BTCUSDT",
        "side": "long" | "short",
        "size": 0.001,  # position size in base asset
        "leverage": 1-10,
        "take_profit_pct": 2.0,
        "stop_loss_pct": 1.0,
        "entry_price": 97000.50
    }
    """
    try:
        from .live_dashboard import get_dashboard, Position
        import time
        
        dashboard = get_dashboard()
        
        symbol = request.get('symbol')
        side = request.get('side')
        size = request.get('size')
        leverage = request.get('leverage', 1)
        tp_pct = request.get('take_profit_pct', 2.0)
        sl_pct = request.get('stop_loss_pct', 1.0)
        entry_price = request.get('entry_price')
        allow_live = request.get('allow_live', False)
        
        # Check if live trading is enabled
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        if allow_live and not live_enabled:
            raise HTTPException(
                status_code=403, 
                detail='Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1 to enable.'
            )
        
        print(f"[MANUAL TRADE] symbol={symbol}, side={side}, size={size}, leverage={leverage}, entry_price={entry_price}, live={allow_live}")
        
        # Validate required fields
        if not all([symbol, side, size, entry_price]):
            raise HTTPException(status_code=400, detail='Missing required fields')
        
        # Convert to proper types
        try:
            size = float(size)
            entry_price = float(entry_price)
            leverage = int(leverage)
            tp_pct = float(tp_pct)
            sl_pct = float(sl_pct)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f'Invalid numeric values: {e}')
        
        if side not in ['long', 'short']:
            raise HTTPException(status_code=400, detail='Side must be "long" or "short"')
        
        # Check if position already exists
        existing_pos = dashboard.get_position(symbol)
        if existing_pos:
            raise HTTPException(status_code=400, detail=f'Position already open for {symbol}')
        
        # Calculate stop-loss and take-profit prices
        if side == 'long':
            stop_loss = entry_price * (1 - sl_pct / 100)
            take_profit = entry_price * (1 + tp_pct / 100)
        else:  # short
            stop_loss = entry_price * (1 + sl_pct / 100)
            take_profit = entry_price * (1 - tp_pct / 100)
        
        # Create position
        market_type = 'futures' if leverage > 1 else 'spot'
        
        # Execute real order on Binance if allow_live=True
        binance_order_id = None
        actual_entry_price = entry_price
        
        if allow_live:
            try:
                import ccxt
                
                # Get API keys
                api_key = os.environ.get('BINANCE_API_KEY', '')
                api_secret = os.environ.get('BINANCE_API_SECRET', '')
                
                if not api_key or not api_secret:
                    raise HTTPException(status_code=400, detail='Binance API keys not configured')
                
                # Initialize exchange
                exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'options': {
                        'defaultType': 'future' if market_type == 'futures' else 'spot',
                    },
                    'enableRateLimit': True,  # Enable built-in rate limiting
                })
                
                # Set leverage for futures (only if needed)
                if market_type == 'futures' and leverage > 1:
                    await asyncio.to_thread(exchange.set_leverage, leverage, symbol)
                
                # Place market order
                order_side = 'buy' if side == 'long' else 'sell'
                position_side = 'LONG' if side == 'long' else 'SHORT'
                
                # For Binance Futures in Hedge Mode, we need to specify positionSide
                order = await asyncio.to_thread(
                    exchange.create_order,
                    symbol,
                    'market',
                    order_side,
                    size,
                    None,
                    {
                        'positionSide': position_side
                    }
                )
                
                binance_order_id = order.get('id')
                actual_entry_price = order.get('average') or order.get('price') or entry_price
                
                # Calculate and track entry fee
                order_value = actual_entry_price * size
                entry_fee = order_value * 0.0004  # Binance Futures taker fee (0.04%)
                dashboard.add_fee_paid(entry_fee)
                
                print(f"[LIVE ORDER] Binance order executed: {binance_order_id}, side={order_side}, size={size}, price={actual_entry_price}")
                print(f"[LIVE ORDER] Order value: ${order_value:.2f}, Entry fee: ${entry_fee:.4f}")
                print(f"[TIMING] Main order: {order_time:.0f}ms")
                
                # Place Stop-Loss and Take-Profit orders in parallel for speed
                async def place_sl_order():
                    if not stop_loss:
                        return None
                    try:
                        sl_side = 'sell' if side == 'long' else 'buy'
                        start = time.time()
                        sl_order = await asyncio.to_thread(
                            exchange.create_order,
                            symbol,
                            'STOP_MARKET',
                            sl_side,
                            size,
                            None,
                            {
                                'stopPrice': stop_loss,
                                'positionSide': position_side,
                                'closePosition': True,
                                'workingType': 'MARK_PRICE'
                            }
                        )
                        sl_time = (time.time() - start) * 1000
                        print(f"[LIVE ORDER] Stop-Loss order placed: {sl_order.get('id')} @ ${stop_loss:.2f} ({sl_time:.0f}ms)")
                        return sl_order
                    except Exception as e:
                        print(f"[ERROR] Failed to place Stop-Loss order: {e}")
                        import traceback
                        traceback.print_exc()
                        return None
                
                async def place_tp_order():
                    if not take_profit:
                        return None
                    try:
                        tp_side = 'sell' if side == 'long' else 'buy'
                        start = time.time()
                        tp_order = await asyncio.to_thread(
                            exchange.create_order,
                            symbol,
                            'TAKE_PROFIT_MARKET',
                            tp_side,
                            size,
                            None,
                            {
                                'stopPrice': take_profit,
                                'positionSide': position_side,
                                'closePosition': True,
                                'workingType': 'MARK_PRICE'
                            }
                        )
                        tp_time = (time.time() - start) * 1000
                        print(f"[LIVE ORDER] Take-Profit order placed: {tp_order.get('id')} @ ${take_profit:.2f} ({tp_time:.0f}ms)")
                        return tp_order
                    except Exception as e:
                        print(f"[ERROR] Failed to place Take-Profit order: {e}")
                        import traceback
                        traceback.print_exc()
                        return None
                
                # Execute SL and TP orders in parallel
                start_sltp = time.time()
                sl_result, tp_result = await asyncio.gather(
                    place_sl_order(),
                    place_tp_order(),
                    return_exceptions=True
                )
                sltp_time = (time.time() - start_sltp) * 1000
                print(f"[TIMING] SL/TP orders: {sltp_time:.0f}ms (parallel)")
                
            except Exception as e:
                print(f"[ERROR] Failed to execute live order on Binance: {e}")
                raise HTTPException(status_code=500, detail=f'Failed to execute order on Binance: {str(e)}')
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=actual_entry_price,
            size=size,
            entry_time=int(time.time() * 1000),
            stop_loss=stop_loss,
            take_profit=take_profit,
            market=market_type,
            is_live=allow_live  # Mark position as live or test
        )
        
        dashboard.open_position(position)
        
        return {
            'success': True,
            'message': f'Manual {side} position opened {"(LIVE)" if allow_live else "(TEST)"}',
            'position': {
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'size': size,
                'leverage': leverage,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to place manual trade: {str(e)}')

@app.post('/api/manual-trade-ws')
async def api_manual_trade_ws(request: dict):
    """
    Place a manual trade using WebSocket API (FASTER).
    This uses ccxt.pro's WebSocket methods for lower latency order execution.
    
    Body: Same as /api/manual-trade
    {
        "symbol": "BTCUSDT",
        "side": "long" | "short",
        "size": 0.001,
        "leverage": 1-10,
        "take_profit_pct": 2.0,
        "stop_loss_pct": 1.0,
        "entry_price": 97000.50,
        "allow_live": true
    }
    """
    try:
        from .live_dashboard import get_dashboard, Position
        import time
        
        dashboard = get_dashboard()
        
        symbol = request.get('symbol')
        side = request.get('side')
        size = request.get('size')
        leverage = request.get('leverage', 1)
        tp_pct = request.get('take_profit_pct', 2.0)
        sl_pct = request.get('stop_loss_pct', 1.0)
        entry_price = request.get('entry_price')
        allow_live = request.get('allow_live', False)
        
        # Check if live trading is enabled
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        if allow_live and not live_enabled:
            raise HTTPException(
                status_code=403, 
                detail='Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1 to enable.'
            )
        
        print(f"[MANUAL TRADE WS] symbol={symbol}, side={side}, size={size}, leverage={leverage}, entry_price={entry_price}, live={allow_live}")
        
        # Validate required fields
        if not all([symbol, side, size, entry_price]):
            raise HTTPException(status_code=400, detail='Missing required fields')
        
        # Convert to proper types
        try:
            size = float(size)
            entry_price = float(entry_price)
            leverage = int(leverage)
            tp_pct = float(tp_pct)
            sl_pct = float(sl_pct)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f'Invalid numeric values: {e}')
        
        if side not in ['long', 'short']:
            raise HTTPException(status_code=400, detail='Side must be "long" or "short"')
        
        # Check if position already exists
        existing_pos = dashboard.get_position(symbol)
        if existing_pos:
            raise HTTPException(status_code=400, detail=f'Position already open for {symbol}')
        
        # Calculate stop-loss and take-profit prices
        if side == 'long':
            stop_loss = entry_price * (1 - sl_pct / 100)
            take_profit = entry_price * (1 + tp_pct / 100)
        else:  # short
            stop_loss = entry_price * (1 + sl_pct / 100)
            take_profit = entry_price * (1 - tp_pct / 100)
        
        # Create position
        market_type = 'futures' if leverage > 1 else 'spot'
        
        # Execute real order on Binance using WebSocket if allow_live=True
        binance_order_id = None
        actual_entry_price = entry_price
        
        if allow_live:
            exchange = None
            session = None
            connector = None
            try:
                import ccxt.pro as ccxtpro
                import aiohttp
                from aiohttp.resolver import ThreadedResolver
                
                # Get API keys
                api_key = os.environ.get('BINANCE_API_KEY', '')
                api_secret = os.environ.get('BINANCE_API_SECRET', '')
                
                if not api_key or not api_secret:
                    raise HTTPException(status_code=400, detail='Binance API keys not configured')
                
                # Create resolver, connector, and session (same as dashboard WebSocket)
                resolver = ThreadedResolver()
                connector = aiohttp.TCPConnector(
                    resolver=resolver,
                    limit=100,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    force_close=False,
                )
                session = aiohttp.ClientSession(connector=connector)
                
                # Initialize WebSocket exchange
                exchange = ccxtpro.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'options': {
                        'defaultType': 'future' if market_type == 'futures' else 'spot',
                    },
                    'enableRateLimit': True,
                    'session': session,
                })
                
                try:
                    # Set leverage for futures (using REST as WS doesn't support this)
                    if market_type == 'futures' and leverage > 1:
                        await asyncio.to_thread(exchange.set_leverage, leverage, symbol)
                    
                    # Place market order via WebSocket - FASTER!
                    order_side = 'buy' if side == 'long' else 'sell'
                    position_side = 'LONG' if side == 'long' else 'SHORT'
                    
                    start = time.time()
                    order = await exchange.create_order_ws(
                        symbol,
                        'market',
                        order_side,
                        size,
                        None,
                        {
                            'positionSide': position_side
                        }
                    )
                    order_time = (time.time() - start) * 1000
                    
                    binance_order_id = order.get('id')
                    actual_entry_price = order.get('average') or order.get('price') or entry_price
                    
                    # Calculate and track entry fee
                    order_value = actual_entry_price * size
                    entry_fee = order_value * 0.0004  # Binance Futures taker fee (0.04%)
                    dashboard.add_fee_paid(entry_fee)
                    
                    print(f"[LIVE ORDER WS] ✅ Binance order executed via WebSocket: {binance_order_id}")
                    print(f"[LIVE ORDER WS] side={order_side}, size={size}, price={actual_entry_price}")
                    print(f"[TIMING WS] Main order: {order_time:.0f}ms")
                    
                    # Place Stop-Loss and Take-Profit orders via HTTP (more reliable than WS for these order types)
                    # Note: Binance doesn't fully support TP/SL via WebSocket yet, so we use HTTP
                    async def place_sl_order_http():
                        if not stop_loss:
                            return None
                        try:
                            sl_side = 'sell' if side == 'long' else 'buy'
                            start = time.time()
                            sl_order = await asyncio.to_thread(
                                exchange.create_order,
                                symbol,
                                'STOP_MARKET',
                                sl_side,
                                size,
                                None,
                                {
                                    'stopPrice': stop_loss,
                                    'positionSide': position_side,
                                    'closePosition': True,
                                    'workingType': 'MARK_PRICE'
                                }
                            )
                            sl_time = (time.time() - start) * 1000
                            print(f"[LIVE ORDER WS] ✅ Stop-Loss placed: {sl_order.get('id')} @ ${stop_loss:.2f} ({sl_time:.0f}ms)")
                            return sl_order
                        except Exception as e:
                            print(f"[ERROR WS] Failed to place Stop-Loss: {e}")
                            return None
                    
                    async def place_tp_order_http():
                        if not take_profit:
                            return None
                        try:
                            tp_side = 'sell' if side == 'long' else 'buy'
                            start = time.time()
                            tp_order = await asyncio.to_thread(
                                exchange.create_order,
                                symbol,
                                'TAKE_PROFIT_MARKET',
                                tp_side,
                                size,
                                None,
                                {
                                    'stopPrice': take_profit,
                                    'positionSide': position_side,
                                    'closePosition': True,
                                    'workingType': 'MARK_PRICE'
                                }
                            )
                            tp_time = (time.time() - start) * 1000
                            print(f"[LIVE ORDER WS] ✅ Take-Profit placed: {tp_order.get('id')} @ ${take_profit:.2f} ({tp_time:.0f}ms)")
                            return tp_order
                        except Exception as e:
                            print(f"[ERROR WS] Failed to place Take-Profit: {e}")
                            return None
                    
                    # Execute SL and TP orders in parallel (HTTP method, more reliable)
                    start_sltp = time.time()
                    sl_result, tp_result = await asyncio.gather(
                        place_sl_order_http(),
                        place_tp_order_http(),
                        return_exceptions=True
                    )
                    sltp_time = (time.time() - start_sltp) * 1000
                    print(f"[TIMING WS] SL/TP orders: {sltp_time:.0f}ms (parallel HTTP)")
                    
                finally:
                    # Proper cleanup: close in reverse order
                    if exchange:
                        await exchange.close()
                    if session:
                        await session.close()
                    if connector:
                        await connector.close()
                    
            except Exception as e:
                print(f"[ERROR WS] Failed to execute live order via WebSocket: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f'Failed to execute order via WebSocket: {str(e)}')
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=actual_entry_price,
            size=size,
            entry_time=int(time.time() * 1000),
            stop_loss=stop_loss,
            take_profit=take_profit,
            market=market_type,
            is_live=allow_live
        )
        
        dashboard.open_position(position)
        
        return {
            'success': True,
            'message': f'Manual {side} position opened via WebSocket {"(LIVE)" if allow_live else "(TEST)"}',
            'position': {
                'symbol': symbol,
                'side': side,
                'entry_price': actual_entry_price,
                'size': size,
                'leverage': leverage,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            },
            'method': 'WebSocket'
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'Failed to place manual trade via WebSocket: {str(e)}')

@app.post('/api/manual-trade/close')
async def api_manual_trade_close(request: dict):
    """Close a manual test position.
    
    Body:
    {
        "symbol": "BTCUSDT",
        "exit_price": 98000.50,
        "allow_live": false
    }
    """
    try:
        from .live_dashboard import get_dashboard
        
        dashboard = get_dashboard()
        
        symbol = request.get('symbol')
        exit_price = request.get('exit_price')
        allow_live = request.get('allow_live', False)
        
        # Check if live trading is enabled
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        if allow_live and not live_enabled:
            raise HTTPException(
                status_code=403, 
                detail='Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1 to enable.'
            )
        
        print(f"[CLOSE POSITION] symbol={symbol}, exit_price={exit_price}, live={allow_live}")
        
        if not all([symbol, exit_price]):
            raise HTTPException(status_code=400, detail='Missing required fields')
        
        # Convert to proper types
        try:
            exit_price = float(exit_price)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f'Invalid exit_price: {e}')
        
        # Get the position before closing to know the side
        position = dashboard.get_position(symbol)
        if not position:
            raise HTTPException(status_code=404, detail=f'No open position found for {symbol}')
        
        # Execute real close order on Binance if allow_live=True
        if allow_live:
            try:
                import ccxt
                
                # Get API keys
                api_key = os.environ.get('BINANCE_API_KEY', '')
                api_secret = os.environ.get('BINANCE_API_SECRET', '')
                
                if not api_key or not api_secret:
                    raise HTTPException(status_code=400, detail='Binance API keys not configured')
                
                # Initialize exchange
                exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'options': {
                        'defaultType': 'future',
                    }
                })
                
                # Close position by placing opposite order
                # If we have a LONG position, we SELL to close
                # If we have a SHORT position, we BUY to close
                close_side = 'sell' if position.side == 'long' else 'buy'
                position_side = 'LONG' if position.side == 'long' else 'SHORT'
                
                # Close the position with reduceOnly=True
                close_order = await asyncio.to_thread(
                    exchange.create_order,
                    symbol,
                    'market',  # Order type
                    close_side,
                    position.size,  # Close the full position
                    None,  # Price (None for market orders)
                    {
                        'positionSide': position_side,  # Must match the position we're closing
                        'reduceOnly': True  # Ensures we only close, not open opposite position
                    }
                )
                
                # Calculate and track exit fee
                actual_exit_price = close_order.get('average') or close_order.get('price') or exit_price
                exit_value = actual_exit_price * position.size
                exit_fee = exit_value * 0.0004  # Binance Futures taker fee (0.04%)
                dashboard.add_fee_paid(exit_fee)
                
                print(f"[LIVE CLOSE] Binance close order executed: {close_order.get('id')}, side={close_side}, positionSide={position_side}")
                print(f"[LIVE CLOSE] Exit value: ${exit_value:.2f}, Exit fee: ${exit_fee:.4f}")
                
            except Exception as e:
                print(f"[ERROR] Failed to close live position on Binance: {e}")
                raise HTTPException(status_code=500, detail=f'Failed to close position on Binance: {str(e)}')
        
        # Close position in dashboard
        trade = dashboard.close_position(symbol, exit_price, reason='manual_close')
        
        if not trade:
            raise HTTPException(status_code=404, detail=f'No open position found for {symbol}')
        
        return {
            'success': True,
            'message': f'Position closed {"(LIVE)" if allow_live else "(TEST)"}',
            'trade': {
                'symbol': trade.symbol,
                'side': trade.side,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'pnl': trade.pnl,
                'pnl_pct': trade.pnl_pct,
                'reason': trade.reason
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to close manual trade: {str(e)}')


@app.post('/api/manual-trade/adjust')
async def api_manual_trade_adjust(request: dict):
    """Adjust stop-loss and take-profit for an open position.
    
    Body:
    {
        "symbol": "BTCUSDT",
        "stop_loss": 97000.00,
        "take_profit": 99000.00,
        "allow_live": false
    }
    """
    try:
        from .live_dashboard import get_dashboard
        
        dashboard = get_dashboard()
        
        symbol = request.get('symbol')
        stop_loss = request.get('stop_loss')
        take_profit = request.get('take_profit')
        allow_live = request.get('allow_live', False)
        
        if not symbol:
            raise HTTPException(status_code=400, detail='Symbol is required')
        
        # Check if live trading is enabled
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        if allow_live and not live_enabled:
            raise HTTPException(
                status_code=403, 
                detail='Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1 to enable.'
            )
        
        # Get the position
        position = dashboard.get_position(symbol)
        if not position:
            raise HTTPException(status_code=404, detail=f'No open position found for {symbol}')
        
        # If live trading, update orders on Binance
        if allow_live:
            try:
                import ccxt
                
                # Get API keys
                api_key = os.environ.get('BINANCE_API_KEY', '')
                api_secret = os.environ.get('BINANCE_API_SECRET', '')
                
                if not api_key or not api_secret:
                    raise HTTPException(status_code=400, detail='Binance API keys not configured')
                
                # Initialize exchange
                exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'options': {
                        'defaultType': 'future',
                    }
                })
                
                position_side = 'LONG' if position.side == 'long' else 'SHORT'
                order_side = 'sell' if position.side == 'long' else 'buy'  # Opposite of entry
                
                # Cancel all existing stop and take-profit orders for this position
                try:
                    open_orders = await asyncio.to_thread(exchange.fetch_open_orders, symbol)
                    for order in open_orders:
                        # Cancel stop-loss and take-profit orders for this position side
                        if order.get('info', {}).get('positionSide') == position_side:
                            order_type = order.get('type', '').upper()
                            if 'STOP' in order_type or 'TAKE_PROFIT' in order_type:
                                await asyncio.to_thread(exchange.cancel_order, order['id'], symbol)
                                print(f"[ADJUST] Cancelled order {order['id']} ({order_type})")
                except Exception as cancel_error:
                    print(f"[WARNING] Failed to cancel existing orders: {cancel_error}")
                
                # Place new Stop-Loss order if provided
                if stop_loss is not None and stop_loss > 0:
                    try:
                        sl_order = await asyncio.to_thread(
                            exchange.create_order,
                            symbol,
                            'STOP_MARKET',
                            order_side,
                            position.size,
                            None,  # No price for STOP_MARKET (uses stopPrice in params)
                            {
                                'stopPrice': float(stop_loss),
                                'positionSide': position_side,
                                'closePosition': True,  # Close position when triggered
                                'workingType': 'MARK_PRICE'
                            }
                        )
                        print(f"[ADJUST] New Stop-Loss order placed: {sl_order.get('id')} @ ${stop_loss:.2f}")
                    except Exception as sl_error:
                        print(f"[WARNING] Failed to place new Stop-Loss: {sl_error}")
                
                # Place new Take-Profit order if provided
                if take_profit is not None and take_profit > 0:
                    try:
                        tp_order = await asyncio.to_thread(
                            exchange.create_order,
                            symbol,
                            'TAKE_PROFIT_MARKET',
                            order_side,
                            position.size,
                            None,  # No price for TAKE_PROFIT_MARKET (uses stopPrice in params)
                            {
                                'stopPrice': float(take_profit),
                                'positionSide': position_side,
                                'closePosition': True,  # Close position when triggered
                                'workingType': 'MARK_PRICE'
                            }
                        )
                        print(f"[ADJUST] New Take-Profit order placed: {tp_order.get('id')} @ ${take_profit:.2f}")
                    except Exception as tp_error:
                        print(f"[WARNING] Failed to place new Take-Profit: {tp_error}")
                
            except Exception as e:
                print(f"[ERROR] Failed to adjust orders on Binance: {e}")
                raise HTTPException(status_code=500, detail=f'Failed to adjust orders on Binance: {str(e)}')
        
        # Update SL/TP in local tracking
        if stop_loss is not None:
            position.stop_loss = float(stop_loss)
        if take_profit is not None:
            position.take_profit = float(take_profit)
        
        print(f"[ADJUST] Updated {symbol} SL/TP: SL=${position.stop_loss:.2f}, TP=${position.take_profit:.2f}")
        
        return {
            'success': True,
            'message': f'SL/TP updated {"(LIVE)" if allow_live else "(TEST)"}',
            'position': {
                'symbol': position.symbol,
                'side': position.side,
                'stop_loss': position.stop_loss,
                'take_profit': position.take_profit
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to adjust SL/TP: {str(e)}')


def _save_webhook_config(obj: dict):
    try:
        with open(_config_path, 'w', encoding='utf-8') as fh:
            json.dump(obj, fh)
    except Exception:
        pass


# Top futures config path and helpers
_top_futures_config_path = os.path.join(ROOT, 'var', 'top_futures_config.json')
os.makedirs(os.path.dirname(_top_futures_config_path), exist_ok=True)
                                                    

def _load_top_futures_config():
    # Defaults mirror the previous env defaults
    defaults = {
        'enabled': True,
        'top_n': 30,
        'lookback_min': 30,
        'threshold_pct': 5.0,
        'run_every_min': 5.0,
        'cooldown_sec': 300,
        'throttle_s': 0.15,
        'exclude_majors': True,
        'majors': list(MAJOR_CAP_USDT),
    }
    try:
        if os.path.exists(_top_futures_config_path):
            with open(_top_futures_config_path, 'r', encoding='utf-8') as fh:
                c = json.load(fh)
                if not isinstance(c, dict):
                    return defaults
                # merge defaults
                out = dict(defaults)
                out.update(c)
                return out
    except Exception:
        pass
    return defaults



def _save_top_futures_config(obj: dict) -> bool:
    try:
        with open(_top_futures_config_path, 'w', encoding='utf-8') as fh:
            json.dump(obj, fh, indent=2)
        return True
    except Exception:
        return False

# Notifier task: watches server_logs for new entries and posts to webhook when enabled
_notifier_task: Optional[asyncio.Task] = None
_last_notified_index: int = 0

# Binance endpoints for quick checks (spot + USDT-M futures)
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
BINANCE_FUTURES_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"

# Background price alerts task
_price_alerts_task: Optional[asyncio.Task] = None
_top_futures_task: Optional[asyncio.Task] = None

# Simple price cache to avoid hammering Binance API
_price_cache: Dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
_price_cache_ttl = 2.0  # Cache for 2 seconds
_vault_apy_monitor_task: Optional[asyncio.Task] = None

# status info for top futures checker
_top_futures_last_run: Optional[str] = None
_top_futures_last_alerts: int = 0
_top_futures_last_error: Optional[str] = None

# default list of major cap USDT futures symbols to exclude from batch checks
MAJOR_CAP_USDT = {
    'BTCUSDT','ETHUSDT','BNBUSDT','XRPUSDT','ADAUSDT','SOLUSDT',
    'DOGEUSDT','MATICUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','TRXUSDT'
}


def _http_get_json_sync(url: str, timeout: float = 10.0):
    try:
        req = _urllib_request.Request(url, headers={"User-Agent": "arb-check/1.0"})
        with _urllib_request.urlopen(req, timeout=timeout) as r:
            response_text = r.read().decode('utf-8')
            return json.loads(response_text)
    except _urllib_error.HTTPError as e:
        # HTTP error (4xx, 5xx)
        error_body = e.read().decode('utf-8') if e.fp else 'No error body'
        print(f"[ERROR] HTTP {e.code} for {url}: {error_body}")
        try:
            server_logs.append({"ts": _dt.datetime.utcnow().isoformat(), "text": f"http {e.code}: {error_body}"})
        except Exception:
            pass
        return None
    except _urllib_error.URLError as e:
        # Network error
        print(f"[ERROR] Network error for {url}: {str(e.reason)}")
        try:
            server_logs.append({"ts": _dt.datetime.utcnow().isoformat(), "text": f"network error: {str(e.reason)}"})
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[ERROR] HTTP request failed for {url}: {str(e)}")
        try:
            server_logs.append({"ts": _dt.datetime.utcnow().isoformat(), "text": f"http error: {str(e)}"})
        except Exception:
            pass
        return None


def _fetch_klines_sync(symbol: str, interval: str = '1m', limit: int = 100, startTime: Optional[int] = None, market: str = 'spot'):
    base = BINANCE_KLINES_URL if market == 'spot' else BINANCE_FUTURES_KLINES_URL
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if startTime is not None:
        params["startTime"] = int(startTime)
    q = _urllib_parse.urlencode(params)
    url = f"{base}?{q}"
    data = _http_get_json_sync(url)
    if not isinstance(data, list):
        return []
    return data


def _fetch_ticker_sync(symbol: str, market: str = 'spot') -> Optional[float]:
    """Fetch current ticker price from Binance with caching."""
    global _price_cache
    
    # Check cache
    cache_key = f"{symbol}_{market}"
    now = time.time()
    if cache_key in _price_cache:
        cached_price, cached_time = _price_cache[cache_key]
        if now - cached_time < _price_cache_ttl:
            return cached_price
    
    try:
        base = BINANCE_TICKER_URL if market == 'spot' else BINANCE_FUTURES_TICKER_URL
        q = _urllib_parse.urlencode({"symbol": symbol})
        url = f"{base}?{q}"
        data = _http_get_json_sync(url)
        if not isinstance(data, dict):
            print(f"[WARNING] Invalid ticker response for {symbol} ({market}): {data}")
            return None
        try:
            price = float(data.get('price'))
            # Cache the result
            _price_cache[cache_key] = (price, now)
            return price
        except Exception as e:
            print(f"[WARNING] Could not parse price for {symbol} ({market}): {data}")
            return None
    except Exception as e:
        print(f"[ERROR] Failed to fetch ticker for {symbol} ({market}): {e}")
        return None


def _closes_from_klines(klines):
    out = []
    for k in klines:
        try:
            out.append(float(k[4]))
        except Exception:
            continue
    return out


def _percent_change(old: float, new: float) -> Optional[float]:
    try:
        if old == 0:
            return None
        return (new - old) / old * 100.0
    except Exception:
        return None


async def _price_alerts_loop():
    """Periodically check price movement for hotcoins in both spot and futures and append alerts to server_logs.

    Simpler implementation: iterate the canonical hot list (or attempt to derive a short list), check each symbol in both
    spot and futures using synchronous helper wrappers via asyncio.to_thread. Per-symbol exceptions are caught so one
    failure doesn't stop the loop.
    """
    global _hot_last_alert_ts
    interval = float(os.environ.get('ARB_HOT_ALERT_CHECK_INTERVAL', '30.0'))
    cooldown = int(os.environ.get('ARB_HOT_ALERT_COOLDOWN_SEC', '300'))
    window_min = int(os.environ.get('ARB_HOT_ALERT_WINDOW_MIN', str(_hot_percent_window_min)))
    threshold = float(os.environ.get('ARB_HOT_ALERT_PCT', str(_hot_percent_threshold)))

    try:
        while True:
            # prepare symbol list
            symbols = list(_hotcoins_agg_last_hot_list) if _hotcoins_agg_last_hot_list else []
            if not symbols:
                try:
                    from .exchanges.mock_exchange import MockExchange
                    ex1 = MockExchange('CEX-A', {})
                    hot_objs = await asyncio.to_thread(find_hot_coins, [ex1])
                    symbols = [s.get('symbol') for s in (hot_objs or []) if isinstance(s, dict) and s.get('symbol')]
                except Exception:
                    symbols = []

            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (window_min * 60 * 1000)
            max_symbols = int(os.environ.get('ARB_HOT_ALERT_MAX_SYMBOLS', '200'))

            for sym in symbols[:max_symbols]:
                for market in ('spot', 'futures'):
                    try:
                        klines = await asyncio.to_thread(_fetch_klines_sync, sym, '1m', window_min + 1, start_ms, market)
                        closes = _closes_from_klines(klines)
                        ticker = await asyncio.to_thread(_fetch_ticker_sync, sym, market)
                        first = closes[0] if len(closes) >= 1 else None
                        if ticker is not None and first is not None:
                            pct = _percent_change(first, ticker)
                        elif len(closes) >= 2:
                            pct = _percent_change(closes[0], closes[-1])
                        else:
                            pct = None

                        if pct is None:
                            continue

                        key = f"{sym}:{market}"
                        last_ts = _hot_last_alert_ts.get(key)
                        now_ts = _dt.datetime.utcnow()
                        allow_alert = True
                        if last_ts:
                            try:
                                last_time = _dt.datetime.fromisoformat(last_ts)
                                if (now_ts - last_time).total_seconds() < cooldown:
                                    allow_alert = False
                            except Exception:
                                allow_alert = True

                        if allow_alert and abs(pct) >= threshold:
                            _hot_last_alert_ts[key] = now_ts.isoformat()
                            text = f"hot move {sym} {market} {pct:.2f}% over {window_min}min"
                            price_ago = first if first is not None else None
                            current_price = ticker if ticker is not None else (closes[-1] if len(closes) else None)
                            entry = {
                                "ts": now_ts.isoformat(),
                                "type": "hotcoin_price_move",
                                "src": "hotcoins",
                                "level": "warning",
                                "symbol": sym,
                                "market": market,
                                "percent": round(pct, 4),
                                "price_ago": price_ago,
                                "current_price": current_price,
                                "text": text,
                                "alerts": [{"symbol": sym, "market": market, "percent": round(pct, 4), "price_ago": price_ago, "current_price": current_price}]
                            }
                            try:
                                server_logs.append(entry)
                            except Exception:
                                pass
                                # Also append a feature_extractor-style entry so Topbar (which listens to feature_extractor)
                                # will count the notification badge. Include both 'feature_extractor' and 'feature-extractor' src
                                fe_entry = dict(entry)
                                fe_entry['src'] = 'feature_extractor'
                                try:
                                    server_logs.append(fe_entry)
                                except Exception:
                                    try:
                                        fe_entry2 = dict(entry)
                                        fe_entry2['src'] = 'feature-extractor'
                                        server_logs.append(fe_entry2)
                                    except Exception:
                                        pass
                    except Exception:
                        # ignore per-symbol errors
                        continue

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return


async def _top_futures_checker_loop():
    """Periodically check top-N Binance futures USDT pairs (excluding majors) and append alerts to server_logs.

    Controlled by environment variables:
      ARB_TOP_FUTURES_ON_STARTUP=1|0   (default 1)
      ARB_TOP_FUTURES_TOP_N            (default 30)
      ARB_TOP_FUTURES_LOOKBACK_MIN     (default 30)
      ARB_TOP_FUTURES_THRESHOLD_PCT    (default 5.0)
      ARB_TOP_FUTURES_RUN_EVERY_MIN    (default 5.0)
    """
    global _top_futures_last_run, _top_futures_last_alerts, _top_futures_last_error
    last_alert_ts: Dict[str, str] = {}

    try:
        while True:
            # load runtime config
            cfg = _load_top_futures_config()
            try:
                _top_futures_last_error = None
            except Exception:
                pass
            if not isinstance(cfg, dict) or not cfg.get('enabled', True):
                await asyncio.sleep(5.0)
                continue

            interval_min = float(cfg.get('run_every_min', 5.0))
            top_n = int(cfg.get('top_n', 30))
            window_min = int(cfg.get('lookback_min', 30))
            threshold = float(cfg.get('threshold_pct', 5.0))
            cooldown = int(cfg.get('cooldown_sec', 300))
            throttle_s = float(cfg.get('throttle_s', 0.15))
            exclude_majors = bool(cfg.get('exclude_majors', True))
            majors_list = set(cfg.get('majors', list(MAJOR_CAP_USDT)))

            # fetch 24h futures tickers
            data = _http_get_json_sync(BINANCE_FUTURES_24H_URL)
            if not isinstance(data, list):
                await asyncio.sleep(max(1.0, interval_min * 60.0))
                continue

            def vol_of(item: dict) -> float:
                try:
                    return float(item.get('quoteVolume') or item.get('volume') or 0.0)
                except Exception:
                    return 0.0

            data_sorted = sorted(data, key=vol_of, reverse=True)
            symbols: list[str] = []
            for item in data_sorted:
                s = item.get('symbol')
                if not s:
                    continue
                if not s.endswith('USDT'):
                    continue
                if exclude_majors and s in majors_list:
                    continue
                symbols.append(s)
                if len(symbols) >= top_n:
                    break

            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (window_min * 60 * 1000)

            alerts_this_run = 0
            for sym in symbols:
                try:
                    klines = await asyncio.to_thread(_fetch_klines_sync, sym, '1m', window_min + 1, start_ms, 'futures')
                    closes = _closes_from_klines(klines)
                    ticker = await asyncio.to_thread(_fetch_ticker_sync, sym, 'futures')

                    first = closes[0] if len(closes) >= 1 else None
                    if ticker is not None and first is not None:
                        pct = _percent_change(first, ticker)
                    elif len(closes) >= 2:
                        pct = _percent_change(closes[0], closes[-1])
                    else:
                        pct = None

                    if pct is None:
                        await asyncio.sleep(throttle_s)
                        continue

                    key = f"topfutures:{sym}"
                    last_ts = last_alert_ts.get(key)
                    now_ts = _dt.datetime.utcnow()
                    allow_alert = True
                    if last_ts:
                        try:
                            last_time = _dt.datetime.fromisoformat(last_ts)
                            if (now_ts - last_time).total_seconds() < cooldown:
                                allow_alert = False
                        except Exception:
                            allow_alert = True

                    if allow_alert and abs(pct) >= threshold:
                        last_alert_ts[key] = now_ts.isoformat()
                        text = f"hot move {sym} futures {pct:.2f}% over {window_min}min"
                        price_ago = first if first is not None else None
                        current_price = ticker if ticker is not None else (closes[-1] if len(closes) else None)
                        entry = {
                            "ts": now_ts.isoformat(),
                            "type": "hotcoin_price_move",
                            "src": "hotcoins",
                            "level": "warning",
                            "symbol": sym,
                            "market": 'futures',
                            "percent": round(pct, 4),
                            "price_ago": price_ago,
                            "current_price": current_price,
                            "text": text,
                            "alerts": [{"symbol": sym, "market": 'futures', "percent": round(pct, 4), "price_ago": price_ago, "current_price": current_price}]
                        }
                        try:
                            server_logs.append(entry)
                            alerts_this_run += 1
                        except Exception:
                            pass
                except Exception:
                    # ignore per-symbol failures
                    pass
                await asyncio.sleep(throttle_s)

            # update status
            try:
                _top_futures_last_run = _dt.datetime.utcnow().isoformat()
                _top_futures_last_alerts = int(alerts_this_run)
            except Exception:
                pass

            await asyncio.sleep(max(1.0, interval_min * 60.0))
    except asyncio.CancelledError:
        return


@app.get('/top-futures/config')
async def get_top_futures_config():
    try:
        return _load_top_futures_config()
    except Exception:
        raise HTTPException(status_code=500, detail='failed to load config')


@app.put('/top-futures/config')
async def put_top_futures_config(req: Request):
    try:
        body = await req.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail='invalid payload')
        ok = _save_top_futures_config(body)
        if not ok:
            raise HTTPException(status_code=500, detail='failed to save config')
        return {'saved': True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='failed to save config')


@app.get('/top-futures/status')
async def get_top_futures_status():
    try:
        return {
            'running': _top_futures_task is not None and not _top_futures_task.done(),
            'last_run': _top_futures_last_run,
            'last_alerts': _top_futures_last_alerts,
            'last_error': _top_futures_last_error,
        }
    except Exception:
        raise HTTPException(status_code=500, detail='failed to fetch status')


@app.post('/top-futures/start')
async def post_top_futures_start():
    global _top_futures_task
    try:
        if _top_futures_task is None or _top_futures_task.done():
            _top_futures_task = asyncio.create_task(_top_futures_checker_loop())
            return {'started': True}
        return {'started': False, 'reason': 'already running'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/top-futures/start')
async def get_top_futures_start():
    return await post_top_futures_start()


@app.post('/top-futures/stop')
async def post_top_futures_stop():
    global _top_futures_task
    try:
        if _top_futures_task is not None and not _top_futures_task.done():
            try:
                _top_futures_task.cancel()
                await _top_futures_task
            except Exception:
                pass
            _top_futures_task = None
            return {'stopped': True}
        return {'stopped': False, 'reason': 'not running'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/top-futures/stop')
async def get_top_futures_stop():
    return await post_top_futures_stop()


@app.post('/top-futures/run')
async def post_top_futures_run():
    """Perform one immediate run of the top-futures checker (synchronous work in thread).

    Returns a summary: {checked: N, alerts: M}
    """
    try:
        cfg = _load_top_futures_config()
        if not isinstance(cfg, dict) or not cfg.get('enabled', True):
            return {'ran': False, 'reason': 'disabled in config'}

        top_n = int(cfg.get('top_n', 30))
        window_min = int(cfg.get('lookback_min', 30))
        threshold = float(cfg.get('threshold_pct', 5.0))
        exclude_majors = bool(cfg.get('exclude_majors', True))
        majors_list = set(cfg.get('majors', list(MAJOR_CAP_USDT)))
        throttle_s = float(cfg.get('throttle_s', 0.15))

        data = _http_get_json_sync(BINANCE_FUTURES_24H_URL)
        if not isinstance(data, list):
            raise Exception('failed to fetch futures 24h tickers')

        def vol_of(item: dict) -> float:
            try:
                return float(item.get('quoteVolume') or item.get('volume') or 0.0)
            except Exception:
                return 0.0

        data_sorted = sorted(data, key=vol_of, reverse=True)
        symbols = []
        for item in data_sorted:
            s = item.get('symbol')
            if not s:
                continue
            if not s.endswith('USDT'):
                continue
            if exclude_majors and s in majors_list:
                continue
            symbols.append(s)
            if len(symbols) >= top_n:
                break

        checked = 0
        alerts = 0
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (window_min * 60 * 1000)
        for sym in symbols:
            checked += 1
            try:
                klines = _fetch_klines_sync(sym, '1m', window_min + 1, start_ms, 'futures')
                closes = _closes_from_klines(klines)
                ticker = _fetch_ticker_sync(sym, 'futures')
                first = closes[0] if len(closes) >= 1 else None
                if ticker is not None and first is not None:
                    pct = _percent_change(first, ticker)
                elif len(closes) >= 2:
                    pct = _percent_change(closes[0], closes[-1])
                else:
                    pct = None
                if pct is None:
                    continue
                if abs(pct) >= threshold:
                    now_ts = _dt.datetime.utcnow()
                    text = f"hot move {sym} futures {pct:.2f}% over {window_min}min"
                    price_ago = first if first is not None else None
                    current_price = ticker if ticker is not None else (closes[-1] if len(closes) else None)
                    entry = {
                        "ts": now_ts.isoformat(),
                        "type": "hotcoin_price_move",
                        "src": "hotcoins",
                        "level": "warning",
                        "symbol": sym,
                        "market": 'futures',
                        "percent": round(pct, 4),
                        "price_ago": price_ago,
                        "current_price": current_price,
                        "text": text,
                        "alerts": [{"symbol": sym, "market": 'futures', "percent": round(pct, 4), "price_ago": price_ago, "current_price": current_price}]
                    }
                    try:
                        server_logs.append(entry)
                        alerts += 1
                    except Exception:
                        pass
            except Exception:
                continue
            time.sleep(throttle_s)

        # update status globals
        try:
            global _top_futures_last_run, _top_futures_last_alerts
            _top_futures_last_run = _dt.datetime.utcnow().isoformat()
            _top_futures_last_alerts = alerts
        except Exception:
            pass

        return {'ran': True, 'checked': checked, 'alerts': alerts}
    except HTTPException:
        raise
    except Exception as e:
        try:
            _top_futures_last_error = str(e)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/top-futures/run')
async def get_top_futures_run():
    return await post_top_futures_run()


@app.get('/api/executions/{run_id}')
async def api_get_execution(run_id: str):
    """Retrieve a persisted execution trace by run_id.

    Returns the JSON content of var/executions/<run_id>.json or 404 if not found.
    """
    try:
        out_dir = os.path.join(ROOT, 'var', 'executions')
        path = os.path.join(out_dir, f"{run_id}.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail='execution-not-found')
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'failed-to-read-execution: {e}')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



async def _notifier_loop():
    global _last_notified_index
    interval = float(os.environ.get('ARB_NOTIFIER_INTERVAL', '1.0'))
    try:
        while True:
            try:
                # snapshot length
                ln = len(server_logs)
                if ln > _last_notified_index and _alerts_enabled and _feature_extractor and getattr(_feature_extractor, 'webhook_url', None):
                    # batch new logs into a single payload and post once
                    batch = []
                    for i in range(_last_notified_index, ln):
                        try:
                            entry = server_logs[i]
                            batch.append(entry)
                        except Exception:
                            continue
                    if batch:
                        payload = {'type': 'server_log_batch', 'count': len(batch), 'logs': batch}
                        try:
                            _feature_extractor._post_webhook(payload)
                        except Exception:
                            pass
                    _last_notified_index = ln
                else:
                    # advance index if logs were trimmed or disabled
                    if ln < _last_notified_index:
                        _last_notified_index = ln
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                try:
                    await asyncio.sleep(interval)
                except Exception:
                    pass
    except asyncio.CancelledError:
        return


# -----------------------------------------------------------------------------
# CCXT instance helper
# -----------------------------------------------------------------------------
async def _get_ccxt_instance(name: str, api_key: Optional[str], secret: Optional[str]):
    """Return a cached CCXTExchange instance or construct one in a thread."""
    key = f"{name}:{'key' if api_key else 'nokey'}:{'secret' if secret else 'nosecret'}"
    inst = _ccxt_instances.get(key)
    if inst is not None:
        return inst
    try:
        from .exchanges.ccxt_adapter import CCXTExchange

        inst = await asyncio.to_thread(CCXTExchange, name, api_key, secret)

        # Instrumentation (best-effort)
        try:
            if hasattr(inst, 'get_tickers'):
                orig_get_tickers = inst.get_tickers

                def wrapped_get_tickers(*a, **kw):
                    try:
                        import time as _time
                        from datetime import datetime as _dt
                        start = _time.time()
                        res = orig_get_tickers(*a, **kw)
                        dur = _time.time() - start
                        server_logs.append({
                            'ts': _dt.utcnow().isoformat(),
                            'text': f'ccxt.get_tickers {getattr(inst, "name", name)} returned {len(res) if hasattr(res, "__len__") else "?"} items in {dur:.2f}s'
                        })
                        return res
                    except Exception as e:
                        from datetime import datetime as _dt
                        server_logs.append({
                            'ts': _dt.utcnow().isoformat(),
                            'text': f'ccxt.get_tickers {getattr(inst, "name", name)} failed: {str(e)}'
                        })
                        raise

                inst.get_tickers = wrapped_get_tickers  # type: ignore[attr-defined]

            if hasattr(inst, 'get_order_book'):
                orig_get_order_book = inst.get_order_book

                def wrapped_get_order_book(sym, depth: int = 10):
                    try:
                        import time as _time
                        from datetime import datetime as _dt
                        start = _time.time()
                        ob = orig_get_order_book(sym, depth=depth)
                        dur = _time.time() - start
                        asks = ob.get('asks', []) if isinstance(ob, dict) else []
                        bids = ob.get('bids', []) if isinstance(ob, dict) else []
                        server_logs.append({
                            'ts': _dt.utcnow().isoformat(),
                            'text': f'ccxt.get_order_book {getattr(inst, "name", name)} {sym} asks={len(asks)} bids={len(bids)} in {dur:.2f}s'
                        })
                        return ob
                    except Exception as e:
                        from datetime import datetime as _dt
                        server_logs.append({
                            'ts': _dt.utcnow().isoformat(),
                            'text': f'ccxt.get_order_book {getattr(inst, "name", name)} {sym} failed: {str(e)}'
                        })
                        raise

                inst.get_order_book = wrapped_get_order_book  # type: ignore[attr-defined]
        except Exception:
            pass

        _ccxt_instances[key] = inst
        return inst
    except Exception:
        pass


@app.post('/api/preview-hedge')
async def api_preview_hedge(request: dict):
    """Preview hedge options for a symbol/notional across candidate exchanges.
    Request: { symbol: 'MYX/USDT', notional: 10000 }
    Returns: list of { exchange, avg_buy_price, avg_sell_price, slippage_buy, slippage_sell, est_6h_net }
    """
    symbol = request.get('symbol')
    notional = float(request.get('notional', 10000))
    if not symbol:
        return JSONResponse({'error': 'symbol required'}, status_code=400)

    # Only compare MEXC and Gate against Binance
    candidates = ['mexc', 'gate']
    results = []
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 24 * 3600 * 1000

    # fetch binance funding via direct call (best-effort)
    try:
        funding = []
        import urllib.request, urllib.parse, ssl
        qs = urllib.parse.urlencode({'symbol': symbol.replace('/', ''), 'startTime': str(start_ms), 'endTime': str(now_ms), 'limit': 1000})
        url = 'https://fapi.binance.com/fapi/v1/fundingRate?' + qs
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            funding = json.loads(resp.read().decode('utf8'))
        total_fund = sum(float(r.get('fundingRate') or 0.0) for r in funding)
        avg_interval = total_fund / len(funding) if funding else 0.0
    except Exception:
        total_fund = 0.0
        avg_interval = 0.0

    # simulate buy on Binance (with timeout)
    try:
        binance = await _get_ccxt_instance('binance', None, None)
        try:
            ob = await asyncio.wait_for(asyncio.to_thread(binance.get_order_book, symbol, 200), timeout=8.0)
        except asyncio.TimeoutError:
            server_logs.append({'ts': _dt.datetime.utcnow().isoformat(), 'text': f'ccxt.get_order_book binance {symbol} timed out'})
            return JSONResponse({'error': 'failed to fetch binance orderbook (timeout)'}, status_code=504)
        asks = ob.get('asks', [])
        # simulate buy consumption
        rem = notional; cost = 0.0; filled_qty = 0.0
        for p, q in asks:
            p = float(p); q = float(q)
            lvl = p * q
            if rem <= 0: break
            take = min(rem, lvl)
            qty = take / p
            cost += qty * p; filled_qty += qty; rem -= take
        avg_buy = cost / filled_qty if filled_qty else None
    except Exception:
        return JSONResponse({'error': 'failed to fetch binance orderbook'}, status_code=500)

    # evaluate candidate hedges in parallel with per-exchange timeouts
    async def _eval_candidate(ex: str):
        start_time = time.time()
        try:
            inst = await _get_ccxt_instance(ex, None, None)
            try:
                ob2 = await asyncio.wait_for(asyncio.to_thread(inst.get_order_book, symbol, 200), timeout=6.0)
                elapsed = time.time() - start_time
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                server_logs.append({'ts': _dt.datetime.utcnow().isoformat(), 'text': f'ccxt.get_order_book {ex} {symbol} timed out after {elapsed:.1f}s'})
                return {'exchange': ex, 'error': 'timeout', 'elapsed_ms': int(elapsed * 1000)}
            
            bids = ob2.get('bids', [])
            if not bids:
                return {'exchange': ex, 'error': 'no bids available', 'elapsed_ms': int(elapsed * 1000)}
            
            rem = notional; cost_s = 0.0; filled_s = 0.0
            for p, q in bids:
                p = float(p); q = float(q)
                lvl = p * q
                if rem <= 0: break
                take = min(rem, lvl)
                qty = take / p
                cost_s += qty * p; filled_s += qty; rem -= take
            
            if filled_s == 0:
                return {'exchange': ex, 'error': 'insufficient liquidity', 'elapsed_ms': int(elapsed * 1000)}
            
            avg_sell = cost_s / filled_s
            slippage_buy = (avg_buy - float(asks[0][0])) / float(asks[0][0]) if asks else 0.0
            slippage_sell = (float(bids[0][0]) - avg_sell) / float(bids[0][0]) if bids else 0.0
            
            # funding income over 6 hours (assume mexc ~ 0 for hedge)
            hours = 6
            bin_hour = -avg_interval if avg_interval < 0 else avg_interval
            funding_income = bin_hour * notional * hours
            fee_rate = 0.0004
            fees = 4 * fee_rate * notional
            slippage_cost = abs((avg_buy - float(asks[0][0])) * filled_qty) + abs((float(bids[0][0]) - avg_sell) * filled_s)
            net = funding_income - fees - slippage_cost
            
            elapsed = time.time() - start_time
            return {
                'exchange': ex, 
                'avg_buy_price': avg_buy, 
                'avg_sell_price': avg_sell, 
                'slippage_buy': slippage_buy, 
                'slippage_sell': slippage_sell, 
                'est_6h_net': net,
                'liquidity_depth': len(bids),
                'elapsed_ms': int(elapsed * 1000)
            }
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            # Make error messages more user-friendly
            if 'timeout' in error_msg.lower():
                error_msg = 'connection timeout'
            elif 'connection' in error_msg.lower():
                error_msg = 'connection failed'
            elif 'symbol' in error_msg.lower():
                error_msg = 'symbol not found'
            return {'exchange': ex, 'error': error_msg, 'elapsed_ms': int(elapsed * 1000)}

    tasks = [asyncio.create_task(_eval_candidate(ex)) for ex in candidates]
    cand_results = await asyncio.gather(*tasks, return_exceptions=True)
    for cr in cand_results:
        # if a task returned an exception object, convert to error entry
        if isinstance(cr, Exception):
            results.append({'exchange': 'unknown', 'error': str(cr)})
        else:
            results.append(cr)

    # sort by est_6h_net desc
    results_sorted = sorted(results, key=lambda r: r.get('est_6h_net') or -999999, reverse=True)

    # funding summary: expose funding rate and 6h estimate
    try:
        funding_rate = float(avg_interval)
    except Exception:
        funding_rate = 0.0
    funding_rate_pct = funding_rate * 100.0
    funding_income_6h = funding_rate * notional * 6.0

    resp = {
        'symbol': symbol,
        'notional': notional,
        'binance_avg_buy': avg_buy,
        'funding_rate': funding_rate,
        'funding_rate_pct': funding_rate_pct,
        'funding_income_6h': funding_income_6h,
        'candidates': results_sorted,
    }

    # also store and broadcast this preview payload so connected frontend
    # clients (Opportunities UI) can display the preview candidates in the
    # cards without requiring the scanner background job to run.
    try:
        global latest_opportunities
        latest_opportunities = resp
        try:
            from datetime import datetime
            server_logs.append({'ts': datetime.utcnow().isoformat(), 'text': 'api: preview_hedge broadcast'})
        except Exception:
            pass
        try:
            await manager.broadcast(json.dumps(resp))
        except Exception:
            pass
    except Exception:
        # best-effort only; do not fail the HTTP response if broadcasting fails
        pass

    return resp


@app.post('/api/run/bear')
async def api_run_bear(request: dict):
    """Run the verbose bear/bull runner as a dry-run for a local CSV symbol.

    Request: { "symbol": "alpineusdt", "mode": "bear" }
    Returns: { status: 'ok', files: [paths], log_tail: [...], stdout: str, stderr: str }
    """
    symbol = (request.get('symbol') or '').strip()
    mode = (request.get('mode') or 'bear').strip().lower()
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol required')
    if mode not in ('bear', 'bull'):
        raise HTTPException(status_code=400, detail='mode must be bear or bull')

    # build CSV path and out prefix
    csv_path = os.path.join(ROOT, 'var', f"{symbol.lower()}_15m.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f'csv not found: {csv_path}')

    out_prefix = f"bear_verbose_{symbol.lower()}"
    cmd = [
        os.environ.get('PYTHON', 'python'),
        os.path.join(ROOT, 'tools', 'run_bear_verbose.py'),
        '--csv', csv_path,
        '--out-prefix', out_prefix,
        '--mode', mode,
    ]

    # run in thread to avoid blocking event loop
    def _run_cmd():
        import subprocess, shlex
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, text=True)
            out, err = proc.communicate(timeout=120)
            return proc.returncode, out, err
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            return 124, '', 'timeout'
        except Exception as e:
            return 1, '', str(e)

    rc, out, err = await asyncio.to_thread(_run_cmd)

    # collect generated file paths (best-effort)
    files = []
    for suffix in ('signals.csv', 'trades.csv', 'equity.csv'):
        p = os.path.join(ROOT, 'var', f"{out_prefix}_{suffix}")
        if os.path.exists(p):
            files.append(p)

    # prepare short tail of stdout/stderr
    def _tail(s: str, lines: int = 20):
        if not s:
            return []
        parts = s.strip().splitlines()
        return parts[-lines:]

    resp = {
        'status': 'ok' if rc == 0 else 'error',
        'returncode': rc,
        'files': files,
        'stdout_tail': _tail(out, 20),
        'stderr_tail': _tail(err, 20),
    }
    # log compact entry
    try:
        server_logs.append({'ts': _dt.datetime.utcnow().isoformat(), 'text': f"api: run_bear {symbol} mode={mode} rc={rc}"})
    except Exception:
        pass

    # If caller requested execution (paper/dry), attempt to run the executor on the produced signals
    exec_flag = bool(request.get('execute'))
    exec_mode = (request.get('exec_mode') or 'paper').strip().lower()
    if exec_flag and exec_mode in ('paper', 'dry'):
        try:
            from .strategy_executor import StrategyExecutor

            # instantiate executor with requested mode
            se = StrategyExecutor(mode=exec_mode)

            # run executor on the signals file we just produced (if present)
            sig_path = os.path.join(ROOT, 'var', f"{out_prefix}_signals.csv")
            if os.path.exists(sig_path):
                # run in a thread to avoid blocking the event loop
                exec_res = await asyncio.to_thread(lambda: se.run_from_signals_file(sig_path, run_id=None, execute=True))
                resp['execution'] = exec_res
            else:
                resp['execution'] = {'error': 'signals file not found', 'path': sig_path}
        except Exception as e:
            resp['execution'] = {'error': str(e)}

    return resp


@app.get('/api/preview-top')
async def api_preview_top(limit: int = 20, notional: float | None = None, symbols: str | None = None, days: int = 3, min_intervals: int = 1):
    """On-demand top preview: compute previews for the current hot/top symbols list.

    Query params:
      - limit: number of top symbols to evaluate (default 20)
      - notional: optional override for the simulation notional (falls back to ARB_PREVIEW_NOTIONAL or 10000)

    This endpoint will compute previews for up to `limit` symbols obtained from the
    hotcoins finder, build a `preview_candidates_top` list (best candidate per symbol),
    broadcast it on the opportunities websocket, and return the detailed per-symbol previews.
    """
    try:
        # determine notional
        preview_notional = None
        try:
            preview_notional = float(notional) if notional is not None else float(os.environ.get('ARB_PREVIEW_NOTIONAL', '10000'))
        except Exception:
            preview_notional = 10000.0

        # Build feeder/exchange list similar to the hotcoins loop
        exchanges_list = []
        try:
            from .exchanges.ws_feed_manager import get_feeder
        except Exception:
            get_feeder = None

        raw = os.environ.get('ARB_HOT_EXCHANGES', 'binance,coinbase,mexc')
        exch_ids = [e.strip() for e in raw.split(',') if e.strip()]
        for eid in exch_ids:
            feeder = None
            try:
                if get_feeder is not None:
                    feeder = get_feeder(eid)
            except Exception:
                feeder = None
            if feeder is not None and hasattr(feeder, 'get_tickers'):
                exchanges_list.append(feeder)

        if not exchanges_list:
            # fallback mock
            ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
            ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
            exchanges_list = [ex1, ex2]

        # If caller supplied an explicit comma-separated `symbols` list, prefer
        # that — the UI can pass a dynamically-updated top list. Otherwise
        # prefer the cached aggregated hot list if available, and finally
        # fall back to calling find_hot_coins.
        try:
            if symbols is not None:
                supplied = [s.strip() for s in symbols.split(',') if s.strip()]
                symbols_to_check = supplied[:int(limit)]
            else:
                # discover top USDT perpetuals by quoteVolume using Binance ticker API
                try:
                    import urllib.request, ssl, json
                    TICKER_API = 'https://fapi.binance.com/fapi/v1/ticker/24hr'
                    ctx = ssl.create_default_context()
                    with urllib.request.urlopen(TICKER_API, context=ctx, timeout=10) as resp:
                        data = resp.read().decode('utf8')
                    tickers = json.loads(data)
                    usdt = [t for t in tickers if t.get('symbol','').endswith('USDT')]
                    usdt_sorted = sorted(usdt, key=lambda t: float(t.get('quoteVolume') or 0.0), reverse=True)
                    # Only fetch the requested limit (default 20) to avoid slow processing
                    pick = usdt_sorted[:int(limit)]
                    symbols_to_check = [p['symbol'] for p in pick]
                except Exception:
                    # fallback to cached hot list or find_hot_coins if discovery fails
                    hot_cached = list(_hotcoins_agg_last_hot_list) if _hotcoins_agg_last_hot_list else []
                    if hot_cached:
                        symbols_to_check = hot_cached[:int(limit)]
                    else:
                        try:
                            hot = await asyncio.to_thread(find_hot_coins, exchanges_list)
                        except Exception:
                            hot = []
                        symbols_to_check = [s for s in (hot or [])][:int(limit)]
        except Exception:
            symbols_to_check = []

        # Build funding-based ranking similar to tools/binance_3day_revenue.py
        try:
            import urllib.request, urllib.parse, ssl
            # allow caller to request different lookback window (default 3 days)
            try:
                days = int(days)
            except Exception:
                days = 3
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - days * 24 * 3600 * 1000
            summaries = []
            # Build list of (orig, bin_sym) pairs where orig is the original object
            # (string or dict) and bin_sym is the canonical symbol string for Binance API
            to_check = []
            for s in symbols_to_check:
                try:
                    orig = s
                    if isinstance(s, dict):
                        # many hotcoin entries are dicts with a 'symbol' field
                        inner = s.get('symbol') or s.get('symbol')
                        cand = inner or ''
                    else:
                        cand = s
                    # canonicalize to Binance style (no separators, uppercase)
                    bin_sym = str(cand).upper().replace('/', '').replace('-', '').replace('_', '')
                    if not bin_sym:
                        continue
                    to_check.append((orig, bin_sym))
                except Exception:
                    continue

            for orig, bin_sym in to_check:
                try:
                    qs = urllib.parse.urlencode({'symbol': bin_sym, 'startTime': str(start_ms), 'endTime': str(now_ms), 'limit': 1000})
                    url = 'https://fapi.binance.com/fapi/v1/fundingRate?' + qs
                    ctx = ssl.create_default_context()
                    # Reduced timeout from 8s to 5s for faster failure
                    with urllib.request.urlopen(url, context=ctx, timeout=5) as resp:
                        funding = json.loads(resp.read().decode('utf8'))
                    total = 0.0
                    last = None
                    count = 0
                    current_funding_rate = 0.0
                    for r in funding:
                        try:
                            fr = float(r.get('fundingRate') or 0.0)
                        except Exception:
                            fr = 0.0
                        total += fr
                        count += 1
                        last = r
                    
                    # Get current funding rate (most recent entry)
                    if last:
                        try:
                            current_funding_rate = float(last.get('fundingRate', 0.0))
                        except Exception:
                            current_funding_rate = 0.0
                    
                    # Fetch current funding rate and next funding time from Binance premiumIndex
                    try:
                        premium_url = f'https://fapi.binance.com/fapi/v1/premiumIndex?symbol={bin_sym}'
                        with urllib.request.urlopen(premium_url, context=ctx, timeout=3) as resp:
                            premium_data = json.loads(resp.read().decode('utf8'))
                            current_funding_rate = float(premium_data.get('lastFundingRate', current_funding_rate))
                            next_funding_time = int(premium_data.get('nextFundingTime', 0))
                    except Exception:
                        # If premium API fails, estimate next funding time (every 8 hours)
                        if last:
                            last_funding_time = int(last.get('fundingTime', 0))
                            # Binance funding happens every 8 hours (0:00, 8:00, 16:00 UTC)
                            next_funding_time = last_funding_time + (8 * 3600 * 1000)
                        else:
                            next_funding_time = now_ms + (8 * 3600 * 1000)
                    
                    # compute revenue similar to Binance UI: use half of notional for perp leg
                    revenue = abs(total) * preview_notional / 2.0
                    apr = (total / max(1, days)) * 365.0 * 100.0
                    # preserve original symbol object in response (so UI can show metadata)
                    # but ensure `symbol` is a string (canonical Binance name) so React
                    # components don't attempt to render an object directly.
                    entry = {
                        'symbol': bin_sym,
                        'bin_symbol': bin_sym,
                        'intervals': count,
                        'cumulative_pct': total * 100.0,
                        'funding_rate_pct': current_funding_rate * 100.0,  # Current funding rate as percentage
                        'revenue_usdt': revenue,
                        'apr_pct': apr,
                        'next_funding_time': next_funding_time,  # Unix timestamp in milliseconds
                        'last': last
                    }
                    try:
                        # if orig is a dict with extra metadata, keep it under `symbol_obj`
                        if isinstance(orig, dict):
                            entry['symbol_obj'] = orig
                    except Exception:
                        pass
                    summaries.append(entry)
                except Exception:
                    # skip problematic symbols but continue
                    continue

            # prefer candidates that have funding intervals (>0) — mirror fetch_binance_funding.py
            # prefer symbols meeting the minimum interval threshold
            try:
                min_intervals = int(min_intervals)
            except Exception:
                min_intervals = 1
            candidates = [s for s in summaries if s.get('intervals', 0) >= min_intervals]
            if candidates:
                # sort by estimated USD revenue descending (most profitable first)
                candidates_sorted = sorted(candidates, key=lambda x: x.get('revenue_usdt', 0.0), reverse=True)
                top_n = int(limit) if limit is not None else 5
                preview_candidates_top = candidates_sorted[:max(1, top_n)]
            else:
                # fallback: use absolute cumulative funding if no symbols meet min_intervals
                candidates_nonzero = [s for s in summaries if s.get('intervals', 0) > 0]
                if candidates_nonzero:
                    candidates_sorted = sorted(candidates_nonzero, key=lambda x: abs(x.get('cumulative_pct', 0.0)), reverse=True)
                    top_n = int(limit) if limit is not None else 5
                    preview_candidates_top = candidates_sorted[:max(1, top_n)]
                else:
                    # last resort: return top by revenue (may be zeros)
                    summaries_sorted = sorted(summaries, key=lambda x: x.get('revenue_usdt', 0.0), reverse=True)
                    top_n = int(limit) if limit is not None else 5
                    preview_candidates_top = summaries_sorted[:max(1, top_n)]

            # broadcast and store
            try:
                global latest_opportunities
                payload = {'preview_candidates_top': preview_candidates_top}
                latest_opportunities = payload
                try:
                    from datetime import datetime
                    server_logs.append({'ts': datetime.utcnow().isoformat(), 'text': 'api: preview_top broadcast'})
                except Exception:
                    pass
                try:
                    await manager.broadcast(json.dumps(payload))
                except Exception:
                    pass
            except Exception:
                pass

            return {'preview_candidates_top': preview_candidates_top}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------
raw_allow = os.environ.get('ARB_ALLOW_ORIGINS', '').strip()
if raw_allow == '*' or raw_allow.upper() == 'ALL':
    allow_origins = ['*']
    allow_credentials = False
elif raw_allow:
    allow_origins = [o.strip() for o in raw_allow.split(',') if o.strip()]
    allow_credentials = True
else:
    allow_origins = ['http://localhost:3000', 'http://127.0.0.1:3000']
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event('startup')
async def _on_startup():
    global _price_alerts_task, _notifier_task, _vault_apy_monitor_task
    # start notifier if not running
    if _notifier_task is None:
        _notifier_task = asyncio.create_task(_notifier_loop())
    # start price alerts loop
    if _price_alerts_task is None:
        _price_alerts_task = asyncio.create_task(_price_alerts_loop())
    # start top futures checker if enabled
    global _top_futures_task
    try:
        run_top = os.environ.get('ARB_TOP_FUTURES_ON_STARTUP', '1').strip() == '1'
    except Exception:
        run_top = True
    if run_top and _top_futures_task is None:
        _top_futures_task = asyncio.create_task(_top_futures_checker_loop())
    # start DeFi vault APY monitor
    global _vault_apy_monitor_task
    if _vault_apy_monitor_task is None:
        _vault_apy_monitor_task = asyncio.create_task(_update_vault_apy_monitor())


@app.on_event('shutdown')
async def _on_shutdown():
    global _price_alerts_task, _notifier_task
    if _price_alerts_task is not None:
        try:
            _price_alerts_task.cancel()
            await _price_alerts_task
        except Exception:
            pass
        _price_alerts_task = None
    if _notifier_task is not None:
        try:
            _notifier_task.cancel()
            await _notifier_task
        except Exception:
            pass
        _notifier_task = None
    # stop top futures checker
    global _top_futures_task
    if _top_futures_task is not None:
        try:
            _top_futures_task.cancel()
            await _top_futures_task
        except Exception:
            pass
        _top_futures_task = None

# -----------------------------------------------------------------------------
# Scanner loop (opportunities)
# -----------------------------------------------------------------------------
async def _scanner_loop():
    """Background scanner loop to compute dry-run opportunities and broadcast."""
    global latest_opportunities
    interval = float(os.environ.get("ARB_SCAN_INTERVAL", "0.8"))

    amount = float(os.environ.get("ARB_DEFAULT_AMOUNT", "1.0"))
    min_profit = float(os.environ.get("ARB_MIN_PROFIT_PCT", "0.01"))
    min_price_diff_pct = float(os.environ.get("ARB_MIN_PRICE_DIFF_PCT", "1.0"))
    use_ccxt = os.environ.get("ARB_USE_CCXT", "0").strip() == "1"

    try:
        while True:
            # Build demo exchanges
            ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
            ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
            ex3 = MockExchange("DEX-X", {"BTC-USD": 50050.0})
            exchanges_list = [ex1, ex2, ex3]

            # Optional CCXT (Binance)
            if use_ccxt:
                try:
                    bin_key = (os.environ.get("BINANCE_API_KEY") or "").strip()
                    bin_secret = (os.environ.get("BINANCE_API_SECRET") or "").strip()
                    if bin_key and bin_secret:
                        cex = await _get_ccxt_instance("binance", bin_key, bin_secret)
                        if cex is not None:
                            exchanges_list.append(cex)
                    else:
                        from datetime import datetime
                        server_logs.append({
                            "ts": datetime.utcnow().isoformat(),
                            "text": "ccxt skipped: missing BINANCE_API_KEY/SECRET"
                        })
                except Exception as e:
                    from datetime import datetime
                    server_logs.append({
                        "ts": datetime.utcnow().isoformat(),
                        "text": f"ccxt import/init failed: {str(e)}"
                    })

            # Compute dry-run opportunities in thread
            opps = await asyncio.to_thread(
                compute_dryrun_opportunities,
                exchanges_list,
                amount,
                min_profit,
                min_price_diff_pct
            )

            payload = {'opportunities': opps}

            # Enrich with preview-hedge estimates for top symbols (optional, lower-frequency heavy work)
            try:
                preview_enabled = os.environ.get('ARB_PREVIEW_ENRICH', '1').strip() == '1'
                preview_top_n = int(os.environ.get('ARB_PREVIEW_TOP_N', '10'))
                preview_notional = float(os.environ.get('ARB_PREVIEW_NOTIONAL', '10000'))
            except Exception:
                preview_enabled = True
                preview_top_n = 10
                preview_notional = 10000.0

            if preview_enabled and opps:
                # collect top symbols by profit_pct
                try:
                    symbols = []
                    seen = set()
                    for o in sorted(opps, key=lambda x: (x.get('profit_pct') or 0), reverse=True):
                        s = o.get('symbol')
                        if not s: continue
                        if s in seen: continue
                        seen.add(s); symbols.append(s)
                        if len(symbols) >= preview_top_n: break

                    async def _compute_preview_for_symbol(symbol: str):
                        candidates = ['mexc', 'kucoin', 'gate', 'okx', 'huobi']
                        now_ms = int(time.time() * 1000)
                        start_ms = now_ms - 24 * 3600 * 1000
                        # fetch binance funding (best-effort)
                        try:
                            funding = []
                            import urllib.request, urllib.parse, ssl
                            qs = urllib.parse.urlencode({'symbol': symbol.replace('/', ''), 'startTime': str(start_ms), 'endTime': str(now_ms), 'limit': 1000})
                            url = 'https://fapi.binance.com/fapi/v1/fundingRate?' + qs
                            ctx = ssl.create_default_context()
                            with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
                                funding = json.loads(resp.read().decode('utf8'))
                            total_fund = sum(float(r.get('fundingRate') or 0.0) for r in funding)
                            avg_interval = total_fund / len(funding) if funding else 0.0
                        except Exception:
                            avg_interval = 0.0

                        # simulate buy on Binance
                        try:
                            binance = await _get_ccxt_instance('binance', None, None)
                            ob = await asyncio.to_thread(binance.get_order_book, symbol, 200)
                            asks = ob.get('asks', [])
                            rem = preview_notional; cost = 0.0; filled_qty = 0.0
                            for p, q in asks:
                                p = float(p); q = float(q)
                                lvl = p * q
                                if rem <= 0: break
                                take = min(rem, lvl)
                                qty = take / p
                                cost += qty * p; filled_qty += qty; rem -= take
                            avg_buy = cost / filled_qty if filled_qty else None
                        except Exception:
                            return {'symbol': symbol, 'error': 'binance orderbook failed'}

                        # evaluate candidates
                        cand_results = []
                        for ex in candidates:
                            try:
                                inst = await _get_ccxt_instance(ex, None, None)
                                ob2 = await asyncio.to_thread(inst.get_order_book, symbol, 200)
                                bids = ob2.get('bids', [])
                                rem = preview_notional; cost_s = 0.0; filled_s = 0.0
                                for p, q in bids:
                                    p = float(p); q = float(q)
                                    lvl = p * q
                                    if rem <= 0: break
                                    take = min(rem, lvl)
                                    qty = take / p
                                    cost_s += qty * p; filled_s += qty; rem -= take
                                avg_sell = cost_s / filled_s if filled_s else None
                                slippage_buy = (avg_buy - float(asks[0][0])) / float(asks[0][0]) if asks else 0.0
                                slippage_sell = (float(bids[0][0]) - avg_sell) / float(bids[0][0]) if bids else 0.0
                                hours = 6
                                bin_hour = -avg_interval if avg_interval < 0 else avg_interval
                                funding_income = bin_hour * preview_notional * hours
                                fee_rate = 0.0004
                                fees = 4 * fee_rate * preview_notional
                                slippage_cost = 0.0
                                try:
                                    slippage_cost = abs((avg_buy - float(asks[0][0])) * filled_qty) + abs((float(bids[0][0]) - avg_sell) * filled_s)
                                except Exception:
                                    slippage_cost = 0.0
                                net = funding_income - fees - slippage_cost
                                cand_results.append({'exchange': ex, 'avg_buy_price': avg_buy, 'avg_sell_price': avg_sell, 'slippage_buy': slippage_buy, 'slippage_sell': slippage_sell, 'est_6h_net': net})
                            except Exception as e:
                                cand_results.append({'exchange': ex, 'error': str(e)})

                        # pick best candidate by est_6h_net
                        best = None
                        try:
                            best = sorted([c for c in cand_results if c.get('est_6h_net') is not None], key=lambda x: x.get('est_6h_net'), reverse=True)[0]
                        except Exception:
                            best = None

                        funding_rate = avg_interval
                        funding_rate_pct = funding_rate * 100.0
                        funding_income_6h = funding_rate * preview_notional * 6.0

                        return {'symbol': symbol, 'binance_avg_buy': avg_buy, 'funding_rate': funding_rate, 'funding_rate_pct': funding_rate_pct, 'funding_income_6h': funding_income_6h, 'candidates': cand_results, 'best': best}

                    # compute previews sequentially (to limit bursts); could be parallelized if needed
                    previews = []
                    for s in symbols:
                        try:
                            p = await _compute_preview_for_symbol(s)
                            previews.append(p)
                        except Exception:
                            continue

                    # build top list by best est_6h_net
                    flat = []
                    for p in previews:
                        b = p.get('best')
                        if b and b.get('est_6h_net') is not None:
                            flat.append({'symbol': p.get('symbol'), 'exchange': b.get('exchange'), 'est_6h_net': b.get('est_6h_net'), 'funding_rate_pct': p.get('funding_rate_pct'), 'binance_avg_buy': p.get('binance_avg_buy')})

                    preview_candidates_top = sorted(flat, key=lambda x: x.get('est_6h_net') or -999999, reverse=True)[:preview_top_n]
                    payload['preview_candidates_top'] = preview_candidates_top
                except Exception:
                    pass

            latest_opportunities = payload

            # Log + broadcast
            try:
                from datetime import datetime
                server_logs.append({
                    "ts": datetime.utcnow().isoformat(),
                    "text": f"scan: {len(opps)} opps, use_ccxt={use_ccxt}"
                })
            except Exception:
                pass

            try:
                await manager.broadcast(json.dumps(payload))
            except Exception:
                pass

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return

# -----------------------------------------------------------------------------
# Hotcoins loop (single, correct implementation)
# -----------------------------------------------------------------------------

async def _hotcoins_loop():
    """Background hot-coins loop: build exchanges list and broadcast hot coins."""
    interval = float(os.environ.get('ARB_HOTCOINS_INTERVAL', '2.0'))
    try:
        try:
            from datetime import datetime
            server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"hotcoins loop starting, interval={interval}"})
        except Exception:
            pass

        while True:
            exchanges_list = []
            try:
                from .exchanges.ws_feed_manager import get_feeder
            except Exception:
                get_feeder = None

            raw = os.environ.get('ARB_HOT_EXCHANGES', 'binance,coinbase,mexc')
            exch_ids = [e.strip() for e in raw.split(',') if e.strip()]

            for eid in exch_ids:
                feeder = None
                try:
                    if get_feeder is not None:
                        feeder = get_feeder(eid)
                except Exception:
                    feeder = None
                if feeder is not None and hasattr(feeder, 'get_tickers'):
                    exchanges_list.append(feeder)

            if not exchanges_list:
                ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
                ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
                ex3 = MockExchange("DEX-X", {"BTC-USD": 50050.0})
                exchanges_list = [ex1, ex2, ex3]

            try:
                hot = await asyncio.to_thread(find_hot_coins, exchanges_list)

                # Enrich using feeder tickers if available (best-effort)
                try:
                    feeders_tickers = {}
                    for ex in exchanges_list:
                        try:
                            name = getattr(ex, 'name', None) or getattr(ex.__class__, '__name__', None)
                            if not name:
                                continue
                            lname = str(name).lower()
                            if hasattr(ex, 'get_tickers'):
                                try:
                                    tk_map = await asyncio.to_thread(ex.get_tickers)
                                except Exception:
                                    tk_map = {}
                                feeders_tickers[lname] = tk_map or {}
                        except Exception:
                            continue

                    def _find_price_in_map(tk_map: dict, symbol: str):
                        if not tk_map or not symbol:
                            return None
                        candidates = [
                            symbol,
                            symbol.replace('/', '-'),
                            symbol.replace('-', '/'),
                            symbol.upper(),
                            symbol.lower(),
                            symbol.replace('-', '').replace('/', '')
                        ]
                        for c in candidates:
                            if c in tk_map:
                                v = tk_map.get(c)
                                try:
                                    if isinstance(v, dict):
                                        for k in ('last', 'price', 'close'):
                                            if k in v and v.get(k) is not None:
                                                return float(v.get(k))
                                    if isinstance(v, (int, float)):
                                        return float(v)
                                    if hasattr(v, 'last'):
                                        return float(getattr(v, 'last'))
                                except Exception:
                                    continue
                        norm = symbol.replace('/', '').replace('-', '').upper()
                        for k, vv in tk_map.items():
                            try:
                                if isinstance(k, str) and k.replace('/', '').replace('-', '').upper() == norm:
                                    if isinstance(vv, dict):
                                        for kk in ('last', 'price', 'close'):
                                            if kk in vv and vv.get(kk) is not None:
                                                return float(vv.get(kk))
                                    if isinstance(vv, (int, float)):
                                        return float(vv)
                            except Exception:
                                continue
                        return None

                    if isinstance(hot, list):
                        for h in hot:
                            try:
                                sym = (h.get('symbol') or '').upper()
                                h['price_binance'] = None
                                h['price_kucoin'] = None
                                h['price_mexc'] = None
                                for feeder_name, tk_map in feeders_tickers.items():
                                    try:
                                        lname = feeder_name.lower()
                                        if 'binance' in lname and h.get('price_binance') is None:
                                            p = _find_price_in_map(tk_map, sym)
                                            if p is not None:
                                                h['price_binance'] = p
                                        if 'kucoin' in lname and h.get('price_kucoin') is None:
                                            p = _find_price_in_map(tk_map, sym)
                                            if p is not None:
                                                h['price_kucoin'] = p
                                        if 'mexc' in lname and h.get('price_mexc') is None:
                                            p = _find_price_in_map(tk_map, sym)
                                            if p is not None:
                                                h['price_mexc'] = p
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                        # After enriching with available feeder prices, record/update price history
                        try:
                            import datetime as _dt
                            now_iso = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()
                            async with _hot_price_history_lock:
                                for h in (hot or []):
                                    try:
                                        sym = (h.get('symbol') or '')
                                        if not sym:
                                            continue
                                        norm = str(sym).upper().replace('/', '').replace('-', '')
                                        # choose the best available price (prefer binance, then others)
                                        price = None
                                        for k in ('price_binance', 'price_kucoin', 'price_mexc'):
                                            try:
                                                v = h.get(k)
                                                if isinstance(v, (int, float)) and v > 0:
                                                    price = float(v)
                                                    break
                                            except Exception:
                                                continue
                                        # fallback: try to parse from a ticker map if available
                                        if price is None:
                                            for tk_map in feeders_tickers.values():
                                                try:
                                                    p = _find_price_in_map(tk_map, sym)
                                                    if p is not None:
                                                        price = p
                                                        break
                                                except Exception:
                                                    continue
                                        if price is None:
                                            continue
                                        # push into history
                                        hist = _hot_price_history.get(norm)
                                        if hist is None:
                                            hist = _deque(maxlen=3600)
                                            _hot_price_history[norm] = hist
                                        hist.append((now_iso, float(price)))
                                    except Exception:
                                        continue
                                # now compute percent moves for top-N (monitor top 50)
                                top_n = 50
                                monitored = (hot or [])[:top_n]
                                cutoff_dt = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc) - _dt.timedelta(minutes=_hot_percent_window_min)
                                for h in monitored:
                                    try:
                                        sym = (h.get('symbol') or '')
                                        if not sym:
                                            continue
                                        norm = str(sym).upper().replace('/', '').replace('-', '')
                                        hist = _hot_price_history.get(norm) or _deque()
                                        if not hist:
                                            continue
                                        # find earliest price >= cutoff
                                        earliest = None
                                        for ts_iso, p in hist:
                                            try:
                                                t = _dt.datetime.fromisoformat(ts_iso)
                                            except Exception:
                                                continue
                                            if t.tzinfo is None:
                                                t = t.replace(tzinfo=_dt.timezone.utc)
                                            if t >= cutoff_dt:
                                                earliest = p
                                                break
                                        if earliest is None:
                                            continue
                                        latest = hist[-1][1]
                                        # basic sanity: must be numeric and > 0
                                        try:
                                            earliest_n = float(earliest)
                                            latest_n = float(latest)
                                        except Exception:
                                            continue
                                        if not (math.isfinite(earliest_n) and math.isfinite(latest_n)):
                                            continue
                                        if earliest_n <= 0 or latest_n <= 0:
                                            # skip obviously invalid samples
                                            continue
                                        # protect against runaway ratios (likely bad data)
                                        if latest_n / earliest_n > 1000 or earliest_n / latest_n > 1000:
                                            # record a debug entry instead of alerting so we can inspect later
                                            try:
                                                from datetime import datetime as _dtnow
                                                server_logs.append({
                                                    'ts': _dtnow.utcnow().isoformat(),
                                                    'level': 'info',
                                                    'src': 'hotcoins',
                                                    'text': f'skipped hotcoin alert for {sym} due to unreasonable price jump (earliest={earliest_n}, latest={latest_n})',
                                                    'meta': {'symbol': sym, 'earliest': earliest_n, 'latest': latest_n, 'hist_sample': list(hist)[-10:]}
                                                })
                                            except Exception:
                                                pass
                                            continue

                                        pct = (latest_n / earliest_n - 1.0) * 100.0
                                        # check threshold
                                        if abs(pct) >= _hot_percent_threshold:
                                            # debounce: only alert once per window per symbol
                                            last = _hot_last_alert_ts.get(norm)
                                            send_alert = False
                                            if not last:
                                                send_alert = True
                                            else:
                                                try:
                                                    last_dt = _dt.datetime.fromisoformat(last)
                                                    if last_dt.tzinfo is None:
                                                        last_dt = last_dt.replace(tzinfo=_dt.timezone.utc)
                                                    if (_dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc) - last_dt).total_seconds() >= (_hot_percent_window_min * 60):
                                                        send_alert = True
                                                except Exception:
                                                    send_alert = True
                                            if send_alert:
                                                try:
                                                    from datetime import datetime as _dtnow
                                                    dir_str = 'up' if pct > 0 else 'down'
                                                    server_logs.append({
                                                        'ts': _dtnow.utcnow().isoformat(),
                                                        'level': 'warning',
                                                        'src': 'hotcoins',
                                                        'text': f'hotcoin {sym} moved {pct:.2f}% {dir_str} in last {_hot_percent_window_min}m',
                                                        'meta': {'symbol': sym, 'pct': pct, 'latest': latest_n, 'earliest': earliest_n, 'hist_sample': list(hist)[-10:]}
                                                    })
                                                    _hot_last_alert_ts[norm] = _dtnow.utcnow().isoformat()
                                                except Exception:
                                                    pass
                                    except Exception:
                                        continue
                        except Exception:
                            pass
                except Exception:
                    pass

                # Broadcast
                try:
                    await hot_manager.broadcast(json.dumps(hot))
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"hotcoins: broadcast {len(hot) if hasattr(hot, '__len__') else '?'} items"})
                except Exception:
                    pass
            except Exception:
                try:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "hotcoins scan failed"})
                except Exception:
                    pass

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return


# -----------------------------------------------------------------------------
# Debug endpoints: alert webhook get/set
# -----------------------------------------------------------------------------
@app.get('/debug/alert_webhook')
async def debug_alert_webhook():
    """Return current alert webhook URL and enabled state."""
    conf = _load_webhook_config()
    return {
        'webhook': getattr(_feature_extractor, 'webhook_url', None) if _feature_extractor else conf.get('url'),
        'enabled': _alerts_enabled or bool(conf.get('enabled')),
        'available': _feature_extractor is not None,
    }


@app.post('/debug/alert_webhook')
async def set_alert_webhook(request: Request):
    """Set or clear the alert webhook URL, and enable/disable alerting.

    JSON body accepted:
      { "url": "https://..." }          -> set webhook URL (empty/null clears)
      { "enable": true|false }          -> toggle alerts on/off
      Combined fields accepted.
    """
    global _alerts_enabled, _feature_extractor
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    url = body.get('url') if isinstance(body, dict) else None
    enable = body.get('enable') if isinstance(body, dict) else None

    if url is not None:
        if _feature_extractor is not None:
            try:
                _feature_extractor.webhook_url = url or None
            except Exception:
                pass

    # persist
    try:
        conf = _load_webhook_config()
        if url is not None:
            conf['url'] = url or None
        if enable is not None:
            conf['enabled'] = bool(enable)
        _save_webhook_config(conf)
    except Exception:
        pass

    if enable is not None:
        _alerts_enabled = bool(enable)

    return {
        'webhook': getattr(_feature_extractor, 'webhook_url', None) if _feature_extractor else None,
        'enabled': _alerts_enabled,
        'available': _feature_extractor is not None,
    }


# Delivery history endpoint removed - delivery attempts are not persisted


async def _hotcoins_agg_loop():
    """Background task: periodically compute hot_by_minute cache using the
    in-memory liquidation buffer and canonical hotcoins list. This reduces
    latency for API callers by avoiding repeated calls to find_hot_coins()."""
    global _hot_by_minute_cache
    interval = float(os.environ.get('ARB_HOT_AGG_INTERVAL', '5.0'))
    window = int(os.environ.get('ARB_HOT_AGG_WINDOW_MIN', str(_hot_by_minute_window_min)))
    try:
        while True:
            try:
                # build hot set once per iteration
                hot_list = await asyncio.to_thread(find_hot_coins)
                hot_set = set()
                def _is_valid_norm(sym: str) -> bool:
                    # Accept only alphanumeric normalized symbols that end with a known quote
                    if not sym or not isinstance(sym, str):
                        return False
                    s = sym.upper()
                    if not s.isalnum():
                        return False
                    quotes = ('USDT', 'BUSD', 'USDC', 'USD', 'BTC', 'ETH')
                    for q in quotes:
                        if s.endswith(q) and len(s) > len(q):
                            base = s[:-len(q)]
                            # base should start with a letter and be at least 2 chars
                            if len(base) >= 2 and base[0].isalpha():
                                return True
                    return False

                for h in (hot_list or []):
                    try:
                        s = (h.get('symbol') or '')
                        if s:
                            norm_s = str(s).upper().replace('/', '').replace('-', '')
                            if _is_valid_norm(norm_s):
                                hot_set.add(norm_s)
                    except Exception:
                        continue

                # compute cutoff and aggregates for the configured window
                import datetime as _dt
                now = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
                cutoff = now - _dt.timedelta(minutes=window)
                # If the canonical hot_set is empty (e.g., no network / feeders),
                # fall back to using symbols observed in the in-memory buffer so
                # the aggregation cache can still be populated in offline/dev.
                if not hot_set:
                    try:
                        for ev in list(_liquidation_buffer):
                            try:
                                msg = ev.get('msg') or {}
                                o = msg.get('o') if isinstance(msg, dict) and 'o' in msg else msg
                                sym = (o.get('s') or o.get('symbol') or '')
                                if sym:
                                    norm = str(sym).upper().replace('/', '').replace('-', '')
                                    try:
                                        if _is_valid_norm(norm):
                                            hot_set.add(norm)
                                    except Exception:
                                        # if validation helper missing or error, fallback to adding
                                        hot_set.add(norm)
                            except Exception:
                                continue
                    except Exception:
                        pass

                temp = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'base_vol': 0.0, 'quote_vol': 0.0}))
                for ev in list(_liquidation_buffer):
                    try:
                        ev_ts = ev.get('ts')
                        parsed = None
                        try:
                            parsed = _dt.datetime.fromisoformat(ev_ts)
                        except Exception:
                            try:
                                parsed = _dt.datetime.utcfromtimestamp(float(ev_ts) / 1000.0).replace(tzinfo=_dt.timezone.utc)
                            except Exception:
                                parsed = None
                        if parsed is None:
                            continue
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
                        if parsed < cutoff:
                            continue
                        minute_iso = parsed.replace(second=0, microsecond=0).isoformat()
                        msg = ev.get('msg') or {}
                        o = msg.get('o') if isinstance(msg, dict) and 'o' in msg else msg
                        sym = (o.get('s') or o.get('symbol') or 'unknown')
                        norm = str(sym).upper().replace('/', '').replace('-', '')
                        if norm not in hot_set:
                            continue
                        qty = 0.0
                        price = 0.0
                        try:
                            qty = float(o.get('q') or o.get('qty') or o.get('z') or 0.0)
                        except Exception:
                            qty = 0.0
                        try:
                            price = float(o.get('ap') or o.get('p') or 0.0)
                        except Exception:
                            price = 0.0
                        # store aggregation under a normalized symbol key so cache
                        # stays consistent (no separators, uppercase)
                        key = norm
                        temp[minute_iso][key]['count'] += 1
                        temp[minute_iso][key]['base_vol'] += qty
                        temp[minute_iso][key]['quote_vol'] += qty * price
                    except Exception:
                        continue

                # swap into cache under lock and set metadata
                try:
                    async with _hot_by_minute_lock:
                        _hot_by_minute_cache = temp
                        try:
                            _hotcoins_agg_last_ts = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()
                        except Exception:
                            _hotcoins_agg_last_ts = None
                        try:
                            # store a compact hot list copy
                            _hotcoins_agg_last_hot_list = list(hot_set)[:200]
                        except Exception:
                            _hotcoins_agg_last_hot_list = []
                except Exception:
                    _hot_by_minute_cache = temp
                    try:
                        _hotcoins_agg_last_ts = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()
                    except Exception:
                        _hotcoins_agg_last_ts = None
                    try:
                        _hotcoins_agg_last_hot_list = list(hot_set)[:200]
                    except Exception:
                        _hotcoins_agg_last_hot_list = []
            except Exception:
                # don't crash the loop
                try:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "hotcoins_agg: iteration failed"})
                except Exception:
                    pass
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return


async def _vol_index_startup_loop():
    """Background task: run the tools/volatility_index.py script once at startup
    (or periodically if ARB_VOL_PERIODIC_MIN is set). This uses a thread to
    call the script's main() to avoid blocking the event loop.
    Control via environment variables:
      ARB_VOL_INDEX_ON_STARTUP=1|0   (default 1)
      ARB_VOL_TOP=N                  (default 40)
      ARB_VOL_INTERVAL=1d|1h         (default 1d)
      ARB_VOL_LOOKBACK=N             (default 30)
      ARB_VOL_HISTORY=path           (default var/hotcoins_vol_history.csv under repo root)
      ARB_VOL_PERIODIC_MIN=minutes   (optional; if set, the task will repeat every N minutes)
    """
    try:
        run_flag = os.environ.get('ARB_VOL_INDEX_ON_STARTUP', '1').strip() == '1'
        if not run_flag:
            return
        # Prepare import path so tools package can be found (repo root)
        try:
            import sys
            if ROOT not in sys.path:
                sys.path.insert(0, ROOT)
        except Exception:
            pass

        try:
            import tools.volatility_index as volmod
        except Exception as e:
            try:
                from datetime import datetime
                server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"vol_index startup: import failed: {str(e)}"})
            except Exception:
                pass
            return

        top = int(os.environ.get('ARB_VOL_TOP', '40'))
        interval = os.environ.get('ARB_VOL_INTERVAL', '1d')
        lookback = int(os.environ.get('ARB_VOL_LOOKBACK', '30'))
        history = os.environ.get('ARB_VOL_HISTORY', os.path.join(ROOT, 'var', 'hotcoins_vol_history.csv'))

        periodic_min = os.environ.get('ARB_VOL_PERIODIC_MIN')
        period_seconds = None
        try:
            if periodic_min is not None and str(periodic_min).strip() != '':
                period_seconds = float(periodic_min) * 60.0
        except Exception:
            period_seconds = None

        # Run at least once, then optionally loop
        while True:
            try:
                # Call the script's main() in a thread so it can perform blocking HTTP I/O
                await asyncio.to_thread(volmod.main, ['--top', str(top), '--interval', interval, '--lookback', str(lookback), '--history', history])
                try:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"vol_index: computed top={top} interval={interval} lookback={lookback} -> history={history}"})
                except Exception:
                    pass
            except SystemExit:
                # volmod.main may call sys.exit(); swallow in thread
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                try:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"vol_index: run failed: {str(e)}"})
                except Exception:
                    pass

            if period_seconds is None:
                break
            try:
                await asyncio.sleep(period_seconds)
            except asyncio.CancelledError:
                break
    except asyncio.CancelledError:
        return
    except asyncio.CancelledError:
        return


# -----------------------------------------------------------------------------
# Position Monitor - Auto-close positions when TP/SL hit
# -----------------------------------------------------------------------------
async def _monitor_positions():
    """Background task to monitor positions and auto-close on TP/SL."""
    print("[POSITION MONITOR] Started")
    while True:
        try:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            from .live_dashboard import get_dashboard
            dashboard = get_dashboard()
            positions = dashboard.get_all_positions()
            
            if not positions:
                continue
            
            for pos in positions:
                try:
                    # Fetch current price
                    market = getattr(pos, 'market', None)
                    if market is None:
                        current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'futures')
                        if not current_price:
                            current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, 'spot')
                    else:
                        current_price = await asyncio.to_thread(_fetch_ticker_sync, pos.symbol, market)
                    
                    if not current_price:
                        continue
                    
                    # Check TP/SL
                    should_close = False
                    close_reason = None
                    
                    if pos.side == 'long':
                        if pos.stop_loss and current_price <= pos.stop_loss:
                            should_close = True
                            close_reason = 'stop_loss'
                        elif pos.take_profit and current_price >= pos.take_profit:
                            should_close = True
                            close_reason = 'take_profit'
                    else:  # short
                        if pos.stop_loss and current_price >= pos.stop_loss:
                            should_close = True
                            close_reason = 'stop_loss'
                        elif pos.take_profit and current_price <= pos.take_profit:
                            should_close = True
                            close_reason = 'take_profit'
                    
                    if should_close:
                        print(f"[POSITION MONITOR] 🎯 Auto-closing {pos.symbol} {pos.side.upper()} position - {close_reason.upper()} hit!")
                        print(f"[POSITION MONITOR] Entry: ${pos.entry_price:.2f}, Current: ${current_price:.2f}, SL: ${pos.stop_loss:.2f}, TP: ${pos.take_profit:.2f}")
                        
                        # Calculate P&L
                        if pos.side == 'long':
                            pnl = (current_price - pos.entry_price) * pos.size
                        else:
                            pnl = (pos.entry_price - current_price) * pos.size
                        
                        # Close position
                        dashboard.close_position(pos.symbol, current_price, close_reason)
                        print(f"[POSITION MONITOR] ✅ Position closed - P&L: ${pnl:.2f}")
                        
                except Exception as e:
                    print(f"[POSITION MONITOR ERROR] Failed to check {pos.symbol}: {e}")
                    
        except Exception as e:
            print(f"[POSITION MONITOR ERROR] Monitor loop failed: {e}")


# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def _start_scanner():
    global _scanner_task, _hotcoins_task, _position_monitor_task, latest_opportunities
    if _scanner_task is not None:
        return

    scanner_enabled = os.environ.get('ARB_ENABLE_SCANNER', '0').strip() == '1'
    hotcoins_enabled = os.environ.get('ARB_ENABLE_HOTCOINS', '1').strip() == '1'
    
    # Start position monitor for automatic TP/SL closure
    _position_monitor_task = asyncio.create_task(_monitor_positions())
    print("[STARTUP] Position monitor task started")

    try:
        from datetime import datetime
        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"scanner starting, ARB_USE_CCXT={os.environ.get('ARB_USE_CCXT','0')}"})
    except Exception:
        pass

    # Initial one-off scan only if scanner enabled
    if scanner_enabled:
        try:
            amount = float(os.environ.get("ARB_DEFAULT_AMOUNT", "1.0"))
            min_profit = float(os.environ.get("ARB_MIN_PROFIT_PCT", "0.01"))
            min_price_diff_pct = float(os.environ.get("ARB_MIN_PRICE_DIFF_PCT", "1.0"))
            use_ccxt = os.environ.get("ARB_USE_CCXT", "0").strip() == "1"

            ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
            ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
            ex3 = MockExchange("DEX-X", {"BTC-USD": 50050.0})
            exchanges_list = [ex1, ex2, ex3]

            if use_ccxt:
                try:
                    bin_key = (os.environ.get("BINANCE_API_KEY") or "").strip()
                    bin_secret = (os.environ.get("BINANCE_API_SECRET") or "").strip()
                    if bin_key and bin_secret:
                        cex = await _get_ccxt_instance("binance", bin_key, bin_secret)
                        if cex is not None:
                            exchanges_list.append(cex)
                    else:
                        from datetime import datetime
                        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "ccxt skipped: missing BINANCE_API_KEY/SECRET"})
                except Exception as e:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"ccxt init (initial scan) failed: {str(e)}"})

            async def _run_initial_scan():
                try:
                    opps = await asyncio.to_thread(
                        compute_dryrun_opportunities,
                        exchanges_list,
                        amount,
                        min_profit,
                        min_price_diff_pct
                    )
                    payload = {'opportunities': opps}
                    globals()['latest_opportunities'] = payload
                    try:
                        from datetime import datetime
                        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"initial scan: {len(opps)} opps, use_ccxt={use_ccxt}"})
                    except Exception:
                        pass
                    try:
                        await manager.broadcast(json.dumps(payload))
                    except Exception:
                        pass
                except Exception as e:
                    from datetime import datetime
                    server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"initial scan failed: {str(e)}"})

            asyncio.create_task(_run_initial_scan())
        except Exception:
            from datetime import datetime
            server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "initial scan: skipped due to startup error"})
    else:
        from datetime import datetime
        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "initial scan skipped: scanner disabled (ARB_ENABLE_SCANNER != 1)"})

    # Start background tasks based on flags
    _scanner_task = asyncio.create_task(_scanner_loop()) if scanner_enabled else None
    _hotcoins_task = asyncio.create_task(_hotcoins_loop()) if hotcoins_enabled else None
    # Start notifier task
    global _notifier_task
    if _notifier_task is None:
        _notifier_task = asyncio.create_task(_notifier_loop())
    # Start the hotcoins aggregation cache loop (always start; it will handle empty buffers)
    global _hotcoins_agg_task
    if _hotcoins_agg_task is None:
        _hotcoins_agg_task = asyncio.create_task(_hotcoins_agg_loop())
    # Start volatility index task (optional)
    global _vol_index_task
    if _vol_index_task is None:
        _vol_index_task = asyncio.create_task(_vol_index_startup_loop())
    if not hotcoins_enabled:
        from datetime import datetime
        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": "hotcoins not started (ARB_ENABLE_HOTCOINS != 1)"})

    # Optionally auto-start feeders (useful if only hotcoins is running)
    try:
        raw_auto = os.environ.get('ARB_AUTO_START_FEEDERS')
        auto_start_feeders = (raw_auto.strip() == '1') if raw_auto is not None else (not scanner_enabled)

        if auto_start_feeders:
            async def _do_auto_start():
                try:
                    try:
                        from .hotcoins import _binance_top_by_volume
                        top = await asyncio.to_thread(_binance_top_by_volume, 50)
                        symbols = []
                        for it in top:
                            try:
                                base = (it.get('base') or '').strip()
                                quote = (it.get('quote') or '').strip()
                                if base and quote:
                                    symbols.append(f"{base}/{quote}")
                            except Exception:
                                continue
                        if not symbols:
                            symbols = ['BTC/USDT', 'ETH/USDT']
                    except Exception:
                        symbols = ['BTC/USDT', 'ETH/USDT', 'BTC-USD', 'ETH-USD']

                    try:
                        global _auto_feeders
                        _auto_feeders = feeders_start_all(interval=1.0, symbols=symbols)
                        server_logs.append({"ts": __import__('datetime').datetime.utcnow().isoformat(), "text": f"auto-started feeders: {list(_auto_feeders.keys())} (subscribed {len(symbols)} symbols)"})
                    except Exception:
                        _auto_feeders = {}
                except Exception:
                    _auto_feeders = {}

            asyncio.create_task(_do_auto_start())
    except Exception:
        pass

@app.on_event("shutdown")
async def _stop_scanner():
    global _scanner_task, _hotcoins_task, _position_monitor_task
    if _scanner_task is not None:
        _scanner_task.cancel()
        _scanner_task = None
    if _hotcoins_task is not None:
        _hotcoins_task.cancel()
        _hotcoins_task = None
    if _position_monitor_task is not None:
        _position_monitor_task.cancel()
        _position_monitor_task = None
        print("[SHUTDOWN] Position monitor task stopped")
    # stop vol index task
    try:
        global _vol_index_task
        if _vol_index_task is not None:
            _vol_index_task.cancel()
            _vol_index_task = None
    except Exception:
        pass
    # stop hotcoins aggregation task as well
    try:
        global _hotcoins_agg_task
        if _hotcoins_agg_task is not None:
            _hotcoins_agg_task.cancel()
            _hotcoins_agg_task = None
    except Exception:
        pass
    try:
        global _auto_feeders
        if '_auto_feeders' in globals() and isinstance(_auto_feeders, dict):
            try:
                feeders_stop_all(_auto_feeders)
            except Exception:
                pass
            _auto_feeders = {}
    except Exception:
        pass
    # stop notifier task
    try:
        global _notifier_task
        if _notifier_task is not None:
            _notifier_task.cancel()
            _notifier_task = None
    except Exception:
        pass
# -----------------------------------------------------------------------------
# WebSocket endpoints
# -----------------------------------------------------------------------------
@app.websocket("/ws/opportunities")
async def ws_opportunities(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send latest snapshot (dict with 'opportunities') or heartbeat
        if latest_opportunities is not None:
            try:
                await websocket.send_text(json.dumps(latest_opportunities))
            except Exception:
                pass
        else:
            try:
                from datetime import datetime
                hb = {"type": "heartbeat", "ts": datetime.utcnow().isoformat()}
                await websocket.send_text(json.dumps(hb))
            except Exception:
                pass
        while True:
            await asyncio.sleep(60.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.websocket("/ws/hotcoins")
async def ws_hotcoins(websocket: WebSocket):
    await hot_manager.connect(websocket)
    try:
        try:
            from datetime import datetime
            hb = {"type": "heartbeat", "ts": datetime.utcnow().isoformat()}
            await websocket.send_text(json.dumps(hb))
        except Exception:
            pass
        while True:
            await asyncio.sleep(60.0)
    except WebSocketDisconnect:
        hot_manager.disconnect(websocket)


@app.websocket("/ws/liquidations")
async def ws_liquidations(websocket: WebSocket):
    """Serve live liquidation (forceOrder) events.

    Behavior:
    - On connect, send recent lines from the tools/ccxt_out/binance_force_orders_ws.log file if present.
    - Keep the connection open; a background tailer (if running) can broadcast new events.
    """
    await liquidation_manager.connect(websocket)
    try:
        # Try to send recent log lines if available
        try:
            log_path = os.path.join(ROOT, 'tools', 'ccxt_out', 'binance_force_orders_ws.log')
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as fh:
                    lines = fh.readlines()[-200:]
                for ln in lines:
                    try:
                        await websocket.send_text(ln.strip())
                    except Exception:
                        break
        except Exception:
            pass

        # keep websocket open
        while True:
            await asyncio.sleep(60.0)
    except WebSocketDisconnect:
        liquidation_manager.disconnect(websocket)


@app.websocket("/ws/live-dashboard")
async def ws_live_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for real-time live trading dashboard updates.
    
    Streams:
    - Balance updates from Binance
    - Position updates (watch positions)
    - Order fills and status
    - P&L updates
    
    Uses ccxt.pro WebSocket API for low-latency updates.
    """
    await websocket.accept()
    
    try:
        import ccxt.pro as ccxtpro
        from .live_dashboard import get_dashboard
        
        # Get API keys
        api_key = os.environ.get('BINANCE_API_KEY', '')
        api_secret = os.environ.get('BINANCE_API_SECRET', '')
        live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
        
        if not live_enabled:
            await websocket.send_json({
                'type': 'error',
                'message': 'Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1'
            })
            await websocket.close()
            return
        
        if not api_key or not api_secret:
            await websocket.send_json({
                'type': 'error',
                'message': 'Binance API keys not configured'
            })
            await websocket.close()
            return
        
        dashboard = get_dashboard()
        exchange = None
        session = None
        connector = None
        
        try:
            # Initialize WebSocket exchange
            # Use ThreadedResolver instead of aiodns to avoid DNS timeout issues on Windows
            import aiohttp
            from aiohttp.resolver import ThreadedResolver
            
            print("[WS] Creating exchange with ThreadedResolver to avoid DNS issues...")
            
            # Create resolver explicitly
            resolver = ThreadedResolver()
            
            # Create connector with the resolver
            connector = aiohttp.TCPConnector(
                resolver=resolver,
                limit=100,
                ttl_dns_cache=300,
                use_dns_cache=True,
                force_close=False,
            )
            
            # Create custom aiohttp session with our connector
            session = aiohttp.ClientSession(connector=connector)
            
            exchange = ccxtpro.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {
                    'defaultType': 'future',
                },
                'enableRateLimit': True,
                'session': session,  # Use our custom session instead of connector
            })
            
            # Pre-load markets to avoid delays during watch_* calls
            print("[WS] Pre-loading market data...")
            try:
                await exchange.load_markets()
                print("[WS] Markets loaded successfully")
            except Exception as e:
                print(f"[WS ERROR] Failed to load markets: {e}")
                import traceback
                traceback.print_exc()
                await websocket.send_json({
                    'type': 'error',
                    'message': f'Failed to connect to Binance: {str(e)}'
                })
                await websocket.close()
                return
            
            await websocket.send_json({
                'type': 'connected',
                'message': 'Connected to Binance WebSocket',
                'timestamp': int(time.time() * 1000)
            })
            
            # Helper function to safely send JSON (checks if WS is still open)
            async def safe_send_json(data):
                """Send JSON only if websocket is still connected"""
                try:
                    await websocket.send_json(data)
                    return True
                except RuntimeError as e:
                    if "close message has been sent" in str(e) or "WebSocket is not connected" in str(e):
                        print("[WS] WebSocket closed, stopping watcher")
                        return False
                    raise
            
            # Start watching balance, positions, and orders
            async def watch_balance():
                """Stream balance updates"""
                while True:
                    try:
                        balance = await exchange.watch_balance()
                        usdt_balance = balance.get('USDT', {})
                        
                        wallet_balance = usdt_balance.get('total', 0.0)
                        net_info = dashboard.calculate_net_balance(wallet_balance, live_only=True)
                        
                        if not await safe_send_json({
                            'type': 'balance',
                            'data': {
                                'wallet_balance': wallet_balance,
                                'unrealized_pnl': net_info['unrealized_pnl'],
                                'realized_pnl': net_info['realized_pnl'],
                                'total_fees_paid': net_info['total_fees_paid'],
                                'net_balance': net_info['net_balance']
                            },
                            'timestamp': int(time.time() * 1000)
                        }):
                            return  # WebSocket closed, exit watcher
                    except Exception as e:
                        print(f"[WS ERROR] Balance watch error: {e}")
                        import traceback
                        traceback.print_exc()
                        await asyncio.sleep(2)  # Wait before retry
            
            async def watch_positions():
                """Stream position updates with SL/TP from dashboard"""
                # Keep track of symbols to watch prices for
                watched_symbols = set()
                
                while True:
                    try:
                        positions = await exchange.watch_positions()
                        print(f"[WS] Received {len(positions)} positions from Binance")
                        
                        # Filter active positions
                        active_positions = [
                            p for p in positions 
                            if float(p.get('contracts', 0)) != 0
                        ]
                        
                        print(f"[WS] Filtered to {len(active_positions)} active positions")
                        
                        # Merge Binance position data with dashboard SL/TP
                        dashboard_positions = []
                        for binance_pos in active_positions:
                            raw_symbol = binance_pos.get('symbol')
                            # Normalize symbol: 'AIA/USDT:USDT' -> 'AIAUSDT'
                            symbol = raw_symbol.replace('/', '').replace(':USDT', '') if raw_symbol else ''
                            watched_symbols.add(raw_symbol)  # Track for price updates
                            
                            side = 'long' if float(binance_pos.get('contracts', 0)) > 0 else 'short'
                            size = abs(float(binance_pos.get('contracts', 0)))
                            entry_price = float(binance_pos.get('entryPrice', 0))
                            
                            # Get latest mark price (this is what we need for live P&L)
                            current_price = float(binance_pos.get('markPrice', 0))
                            
                            # Calculate P&L manually (like test positions)
                            if side == 'long':
                                unrealized_pnl = (current_price - entry_price) * size
                            else:  # short
                                unrealized_pnl = (entry_price - current_price) * size
                            
                            # Get SL/TP from dashboard tracking (using normalized symbol)
                            # NOTE: In hedge mode, dashboard doesn't distinguish LONG vs SHORT
                            # So we just use the symbol lookup (will match first position)
                            dashboard_pos = dashboard.get_position(symbol)
                            
                            # If position doesn't exist in dashboard, create it
                            # This ensures ticker watcher can find positions
                            if not dashboard_pos:
                                from arbitrage.live_dashboard import Position
                                
                                dashboard_pos = Position(
                                    symbol=symbol,
                                    side=side,
                                    size=size,
                                    entry_price=entry_price,
                                    entry_time=int(time.time() * 1000),
                                    stop_loss=None,
                                    take_profit=None,
                                    market='futures',
                                    is_live=True,  # Mark as live position from exchange
                                )
                                # Add to dashboard (bypassing open_position to avoid fee deduction)
                                with dashboard._lock:
                                    dashboard._positions[symbol] = dashboard_pos
                                
                                # Handle leverage for logging
                                leverage_value = binance_pos.get('leverage')
                                if leverage_value is None:
                                    leverage_value = 1
                                else:
                                    try:
                                        leverage_value = int(float(leverage_value))
                                    except (ValueError, TypeError):
                                        leverage_value = 1
                                
                                print(f"[WS] ✅ Added live position to dashboard: {symbol} {side} (leverage: {leverage_value}x)")
                            
                            stop_loss = dashboard_pos.stop_loss if dashboard_pos else None
                            take_profit = dashboard_pos.take_profit if dashboard_pos else None
                            entry_time = dashboard_pos.entry_time if dashboard_pos else 0
                            
                            # Calculate P&L percentage
                            unrealized_pnl_pct = 0.0
                            if entry_price > 0 and size > 0:
                                unrealized_pnl_pct = (unrealized_pnl / (entry_price * size)) * 100
                            
                            # Get leverage safely
                            leverage_value = binance_pos.get('leverage', 1)
                            if leverage_value is None:
                                leverage_value = 1
                            else:
                                try:
                                    leverage_value = int(float(leverage_value))
                                except (ValueError, TypeError):
                                    leverage_value = 1
                            
                            dashboard_positions.append({
                                'symbol': symbol,
                                'side': side,
                                'entry_price': entry_price,
                                'size': size,
                                'unrealized_pnl': unrealized_pnl,
                                'unrealized_pnl_pct': unrealized_pnl_pct,
                                'leverage': leverage_value,
                                'liquidation_price': binance_pos.get('liquidationPrice', 0),
                                'stop_loss': stop_loss,
                                'take_profit': take_profit,
                                'entry_time': entry_time,
                                'current_price': current_price,
                                # Add unique identifier for hedge mode (symbol + side)
                                'position_id': f"{symbol}_{side.upper()}",
                            })
                            
                            # Update dashboard position with latest price
                            if dashboard_pos and current_price > 0:
                                dashboard_pos.update_pnl(current_price)
                        
                        # Create debug string for logging
                        position_ids = [f"{p['symbol']}_{p['side'].upper()}" for p in dashboard_positions]
                        print(f"[WS] Sending {len(dashboard_positions)} positions to frontend: {position_ids}")

                        
                        if not await safe_send_json({
                            'type': 'positions',
                            'data': dashboard_positions,
                            'count': len(dashboard_positions),
                            'timestamp': int(time.time() * 1000)
                        }):
                            return  # WebSocket closed, exit watcher
                    except Exception as e:
                        print(f"[WS ERROR] Position watch error: {e}")
                        import traceback
                        traceback.print_exc()
                        # Wait before retry to avoid rapid error loops
                        await asyncio.sleep(2)
            
            async def watch_orders():
                """Stream order updates (fills, cancellations, etc.)"""
                while True:
                    try:
                        orders = await exchange.watch_orders()
                        
                        # Send order updates
                        order_updates = []
                        for order in orders:
                            order_updates.append({
                                'id': order.get('id'),
                                'symbol': order.get('symbol'),
                                'type': order.get('type'),
                                'side': order.get('side'),
                                'status': order.get('status'),
                                'price': order.get('price'),
                                'amount': order.get('amount'),
                                'filled': order.get('filled'),
                                'remaining': order.get('remaining'),
                                'timestamp': order.get('timestamp')
                            })
                        
                        if not await safe_send_json({
                            'type': 'orders',
                            'data': order_updates,
                            'timestamp': int(time.time() * 1000)
                        }):
                            return  # WebSocket closed, exit watcher
                    except Exception as e:
                        print(f"[WS ERROR] Orders watch error: {e}")
                        import traceback
                        traceback.print_exc()
                        await asyncio.sleep(2)  # Wait before retry
            
            async def watch_tickers_for_pnl():
                """
                Watch ticker price updates for real-time P&L calculation.
                Uses concurrent tasks to watch multiple symbols simultaneously.
                """
                print("[WS] ⚡ Starting ticker watcher for real-time P&L updates")
                
                active_watchers = {}  # raw_symbol -> asyncio.Task
                
                async def watch_single_ticker(raw_symbol: str):
                    """Watch a single ticker continuously"""
                    print(f"[WS] 📊 Starting continuous ticker stream for {raw_symbol}")
                    while True:
                        try:
                            # Check if WebSocket is still connected before watching
                            # This prevents blocking on watch_ticker when WS is already closed
                            if websocket.client_state.name != 'CONNECTED':
                                print(f"[WS] WebSocket not connected, stopping ticker watcher for {raw_symbol}")
                                break
                            
                            # This blocks until next update for this symbol (streaming)
                            ticker = await exchange.watch_ticker(raw_symbol)
                            current_price = float(ticker.get('last', 0) or ticker.get('mark', 0))
                            
                            if current_price == 0:
                                continue
                            
                            # Get all positions for this symbol
                            all_positions = dashboard.get_all_positions()
                            
                            for pos in all_positions:
                                if not pos.is_live:
                                    continue
                                
                                symbol = pos.symbol
                                pos_raw_symbol = f"{symbol[:-4]}/{symbol[-4:]}:{symbol[-4:]}"
                                
                                if pos_raw_symbol != raw_symbol:
                                    continue
                                
                                # Calculate P&L for this position
                                side = pos.side
                                size = pos.size
                                entry_price = pos.entry_price
                                
                                if side == 'long':
                                    unrealized_pnl = (current_price - entry_price) * size
                                else:
                                    unrealized_pnl = (entry_price - current_price) * size
                                
                                unrealized_pnl_pct = 0.0
                                if entry_price > 0 and size > 0:
                                    unrealized_pnl_pct = (unrealized_pnl / (entry_price * size)) * 100
                                
                                position_id = f"{symbol}_{side.upper()}"
                                
                                # Send real-time P&L update
                                if not await safe_send_json({
                                    'type': 'pnl_update',
                                    'data': {
                                        'symbol': symbol,
                                        'side': side,
                                        'position_id': position_id,
                                        'current_price': current_price,
                                        'unrealized_pnl': unrealized_pnl,
                                        'unrealized_pnl_pct': unrealized_pnl_pct,
                                        'stop_loss': pos.stop_loss,
                                        'take_profit': pos.take_profit,
                                    },
                                    'timestamp': int(time.time() * 1000)
                                }):
                                    print(f"[WS] WebSocket closed while sending P&L for {raw_symbol}")
                                    return  # WebSocket closed
                                
                        except Exception as e:
                            if "close message" not in str(e).lower():
                                print(f"[WS] Ticker watch error for {raw_symbol}: {e}")
                            break  # Exit this watcher task
                
                # Main management loop
                while True:
                    try:
                        # Get current positions
                        all_positions = dashboard.get_all_positions()
                        
                        print(f"[WS] 🔍 Checking positions... Found {len(all_positions)} total")
                        
                        # Find symbols we need to watch
                        needed_symbols = set()
                        for pos in all_positions:
                            if pos.is_live:
                                symbol = pos.symbol
                                raw_symbol = f"{symbol[:-4]}/{symbol[-4:]}:{symbol[-4:]}"
                                needed_symbols.add(raw_symbol)
                                print(f"[WS] 📍 Found live position: {symbol} ({pos.side}) - will watch {raw_symbol}")
                        
                        print(f"[WS] 📡 Need to watch {len(needed_symbols)} symbols: {needed_symbols}")
                        
                        # Start watchers for new symbols
                        for raw_symbol in needed_symbols:
                            # Check if watcher exists and is still running
                            if raw_symbol in active_watchers:
                                task = active_watchers[raw_symbol]
                                if task.done():
                                    # Task completed/crashed, restart it
                                    print(f"[WS] ⚠️ Ticker watcher for {raw_symbol} stopped, restarting...")
                                    try:
                                        # Get exception if task failed
                                        exc = task.exception()
                                        if exc:
                                            print(f"[WS] Task exception: {exc}")
                                    except:
                                        pass
                                    del active_watchers[raw_symbol]
                            
                            if raw_symbol not in active_watchers:
                                print(f"[WS] ✅ Starting ticker watcher for {raw_symbol}")
                                task = asyncio.create_task(watch_single_ticker(raw_symbol))
                                active_watchers[raw_symbol] = task
                        
                        # Stop watchers for symbols no longer needed
                        for raw_symbol in list(active_watchers.keys()):
                            if raw_symbol not in needed_symbols:
                                print(f"[WS] Stopping ticker watcher for {raw_symbol}")
                                active_watchers[raw_symbol].cancel()
                                del active_watchers[raw_symbol]
                        
                        # Check every 5 seconds for position changes
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        if "close message" not in str(e).lower():
                            print(f"[WS ERROR] Ticker watcher main loop error: {e}")
                        await asyncio.sleep(2)
            
            # Run all watchers concurrently (including ticker watcher for real-time P&L)
            await asyncio.gather(
                watch_balance(),
                watch_positions(),
                watch_orders(),
                watch_tickers_for_pnl(),
                return_exceptions=True
            )
            
        finally:
            # Proper cleanup: close in reverse order of creation
            print("[WS] Cleaning up WebSocket resources...")
            if exchange:
                try:
                    await exchange.close()
                    print("[WS] Exchange closed")
                except Exception as e:
                    print(f"[WS] Error closing exchange: {e}")
            
            if session:
                try:
                    await session.close()
                    print("[WS] Session closed")
                except Exception as e:
                    print(f"[WS] Error closing session: {e}")
            
            if connector:
                try:
                    await connector.close()
                    print("[WS] Connector closed")
                except Exception as e:
                    print(f"[WS] Error closing connector: {e}")
                
    except WebSocketDisconnect:
        print("[WS] Live dashboard client disconnected")
    except Exception as e:
        print(f"[WS ERROR] Live dashboard error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                'type': 'error',
                'message': str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
            print("[WS] WebSocket closed")
        except:
            pass


# -----------------------------------------------------------------------------
# Logs endpoints: ingest logs (POST) and list recent logs (GET)
# -----------------------------------------------------------------------------
@app.post('/logs')
async def ingest_log(request: Request):
    """Ingest a structured log entry (JSON) and append to server_logs.

    Accepts JSON body with free-form dict. Adds server-side timestamp 'ts'.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json')
    try:
        from datetime import datetime
        entry = dict(data) if isinstance(data, dict) else {'msg': str(data)}
        if 'ts' not in entry:
            # use millisecond precision and explicit Z (UTC) so JS Date.parse accepts the string
            entry['ts'] = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
        else:
            # Normalize client-provided timestamps to millisecond ISO + 'Z'. Accept several
            # common variants and sanitize them (e.g. '+00:00Z' or '+00:00').
            try:
                raw = str(entry.get('ts') or '')
                # sanitize common broken suffixes
                raw = raw.replace('+00:00Z', 'Z').replace('+00:00', 'Z')
                # try to parse using fromisoformat; if it fails, fallback to utcnow
                try:
                    dt = datetime.fromisoformat(raw)
                except Exception:
                    # last resort: if raw lacks trailing Z, strip fractional seconds to milliseconds
                    try:
                        if raw.endswith('Z'):
                            dt = datetime.fromisoformat(raw.replace('Z', ''))
                        else:
                            dt = datetime.fromisoformat(raw)
                    except Exception:
                        dt = datetime.utcnow()
                # reformat with millisecond precision and explicit Z
                entry['ts'] = dt.isoformat(timespec='milliseconds') + 'Z'
            except Exception:
                entry['ts'] = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
        server_logs.append(entry)
        return {'ok': True, 'entry': entry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/debug/broadcast_opps')
async def debug_broadcast_opps(request: Request):
    """Debug endpoint: accept a JSON payload and broadcast it on /ws/opportunities.

    Useful for UI testing. The payload is stored in `latest_opportunities` and
    broadcast to connected clients via the existing manager.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json')
    try:
        global latest_opportunities
        latest_opportunities = data
        # append a short server log entry for visibility
        try:
            from datetime import datetime
            server_logs.append({'ts': datetime.utcnow().isoformat(), 'text': 'debug broadcast_opps'})
        except Exception:
            pass
        # attempt broadcast (best-effort)
        try:
            await manager.broadcast(json.dumps(data))
        except Exception:
            pass
        return {'broadcasted': True, 'ok': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/logs')
async def list_logs(limit: int = 200):
    """Return most recent logs (up to limit)."""
    try:
        ln = len(server_logs)
        start = max(0, ln - int(limit))
        recent = list(server_logs)[start:]
        # Normalize ts to millisecond precision strings for clients (Topbar uses Date.parse)
        out = []
        from datetime import datetime
        for e in recent:
            ee = dict(e) if isinstance(e, dict) else e
            try:
                ts = ee.get('ts')
                if isinstance(ts, str):
                    # Attempt to parse then reformat to milliseconds
                    try:
                        dt = datetime.fromisoformat(ts)
                        ee['ts'] = dt.isoformat(timespec='milliseconds') + 'Z'
                    except Exception:
                        # leave as-is if parsing fails
                        pass
            except Exception:
                pass
            out.append(ee)
        return {'count': len(out), 'logs': out}
    except Exception:
        return {'count': 0, 'logs': []}


@app.post('/liquidations/ingest')
async def ingest_liquidation(request: Request):
    """Ingest a single liquidation event posted by an external listener.

    Expected JSON: {ts: ISOstring, msg: {...}} or same shape the listener writes to log.
    """
    try:
        obj = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json')
    # basic validation
    if not isinstance(obj, dict) or 'msg' not in obj:
        raise HTTPException(status_code=400, detail='missing msg')
    # normalize ts
    ts = obj.get('ts') or __import__('datetime').datetime.utcnow().isoformat()
    # push into in-memory buffer
    try:
        _liquidation_buffer.append({'ts': ts, 'msg': obj.get('msg')})
    except Exception:
        pass
    # broadcast to websocket clients as a JSON string
    try:
        await liquidation_manager.broadcast(json.dumps(obj))
    except Exception:
        pass
    return {'status': 'ok'}


@app.post('/api/liquidations/ingest')
async def ingest_liquidation_api(request: Request):
    """Compatibility alias for tools that forward to /api/liquidations/ingest.

    Simply delegate to the main ingest_liquidation handler.
    """
    return await ingest_liquidation(request)


@app.get('/liquidations/ingest')
async def ingest_liquidation_info():
    return {
        'detail': "POST endpoint. Send JSON payload {ts:..., msg:{...}} to ingest liquidation events. Use POST to /liquidations/ingest or /api/liquidations/ingest."
    }


@app.get('/api/liquidations/ingest')
async def ingest_liquidation_api_info():
    return {
        'detail': "POST endpoint. Send JSON payload {ts:..., msg:{...}} to ingest liquidation events. Use POST to /liquidations/ingest or /api/liquidations/ingest."
    }


@app.get('/api/liquidations/summary')
async def liquidation_summary(minutes: int = 10, min_qty: float = 0.0):
    """Return per-minute aggregated stats for the last `minutes` minutes.

    Response shape: { 'by_minute': {minute_iso: {symbol: {count, base_vol, quote_vol}}} }
    """
    import datetime as _dt
    now = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    cutoff = now - _dt.timedelta(minutes=minutes)

    # collect events from buffer (all symbols)
    aggregates = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'base_vol': 0.0, 'quote_vol': 0.0}))
    for ev in list(_liquidation_buffer):
        try:
            ev_ts = ev.get('ts')
            # parse ts
            parsed = None
            try:
                parsed = _dt.datetime.fromisoformat(ev_ts)
            except Exception:
                try:
                    parsed = _dt.datetime.utcfromtimestamp(float(ev_ts) / 1000.0).replace(tzinfo=_dt.timezone.utc)
                except Exception:
                    parsed = None
            if parsed is None:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            if parsed < cutoff:
                continue
            minute_iso = parsed.replace(second=0, microsecond=0).isoformat()
            msg = ev.get('msg') or {}
            o = msg.get('o') if isinstance(msg, dict) and 'o' in msg else msg
            sym = (o.get('s') or o.get('symbol') or 'unknown').upper()
            qty = 0.0
            price = 0.0
            try:
                qty = float(o.get('q') or o.get('qty') or o.get('z') or 0.0)
            except Exception:
                qty = 0.0
            try:
                price = float(o.get('ap') or o.get('p') or 0.0)
            except Exception:
                price = 0.0
            if qty < min_qty:
                continue
            aggregates[minute_iso][sym]['count'] += 1
            aggregates[minute_iso][sym]['base_vol'] += qty
            aggregates[minute_iso][sym]['quote_vol'] += qty * price
        except Exception:
            continue

    # Prefer returning the cached hotcoins per-minute aggregates to reduce latency.
    hot_by_minute = None
    try:
        async with _hot_by_minute_lock:
            # make a shallow copy for return to avoid exposing internal structures
            hot_by_minute = {k: dict(v) for k, v in _hot_by_minute_cache.items()} if _hot_by_minute_cache else None
    except Exception:
        try:
            hot_by_minute = {k: dict(v) for k, v in _hot_by_minute_cache.items()} if _hot_by_minute_cache else None
        except Exception:
            hot_by_minute = None

    # If cache missing/empty, fall back to computing hot_by_minute on the fly (compatibility)
    if not hot_by_minute:
        try:
            hot_list = await asyncio.to_thread(find_hot_coins)
            hot_set = set()
            for h in (hot_list or []):
                try:
                    s = (h.get('symbol') or '')
                    if s:
                        hot_set.add(str(s).upper().replace('/', '').replace('-', ''))
                except Exception:
                    continue
            hot_by_minute = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'base_vol': 0.0, 'quote_vol': 0.0}))
            for minute_iso, symmap in aggregates.items():
                for sym, stats in symmap.items():
                    try:
                        norm = str(sym).upper().replace('/', '').replace('-', '')
                        if norm in hot_set:
                            hot_by_minute[minute_iso][sym]['count'] += stats.get('count', 0)
                            hot_by_minute[minute_iso][sym]['base_vol'] += stats.get('base_vol', 0.0)
                            hot_by_minute[minute_iso][sym]['quote_vol'] += stats.get('quote_vol', 0.0)
                    except Exception:
                        continue
        except Exception:
            hot_by_minute = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'base_vol': 0.0, 'quote_vol': 0.0}))

    # Build hot_rankings: cumulative USD volume per symbol split into long/short
    # long = SELL side (exchange sold to close LONG -> traders long liquidated)
    # short = BUY side (exchange bought to close SHORT -> traders short liquidated)
    try:
        # First, collect canonical hot set used for computing hot_by_minute (attempt to reuse cache metadata)
        hot_set = set()
        try:
            # use cached hot list if available
            if _hotcoins_agg_last_hot_list:
                hot_set = {s.upper().replace('/', '').replace('-', '') for s in _hotcoins_agg_last_hot_list}
            else:
                hot_list_tmp = await asyncio.to_thread(find_hot_coins)
                for h in (hot_list_tmp or []):
                    try:
                        s = (h.get('symbol') or '')
                        if s:
                            hot_set.add(str(s).upper().replace('/', '').replace('-', ''))
                    except Exception:
                        continue
        except Exception:
            hot_set = set()

        # accumulate volumes across the requested window
        long_totals = defaultdict(float)
        short_totals = defaultdict(float)
        # iterate the same aggregates we already computed (which are for the requested minutes)
        for minute_iso, symmap in aggregates.items():
            for sym, stats in symmap.items():
                try:
                    norm = str(sym).upper().replace('/', '').replace('-', '')
                    if hot_set and norm not in hot_set:
                        continue
                    # we don't have side info in aggregates, so derive by scanning buffer for this minute
                    # scan matching events for this minute and accumulate side-specific USD
                    # Note: this is potentially heavier but limited to matching minute buckets
                    import datetime as _dt
                    # parse minute_iso into datetime
                    try:
                        minute_dt = _dt.datetime.fromisoformat(minute_iso)
                        if minute_dt.tzinfo is None:
                            minute_dt = minute_dt.replace(tzinfo=_dt.timezone.utc)
                    except Exception:
                        minute_dt = None
                    if minute_dt is None:
                        continue
                    start_ts = minute_dt
                    end_ts = minute_dt + _dt.timedelta(minutes=1)
                    # scan buffer for events in this minute matching symbol
                    for ev in list(_liquidation_buffer):
                        try:
                            ev_ts = ev.get('ts')
                            parsed = None
                            try:
                                parsed = _dt.datetime.fromisoformat(ev_ts)
                            except Exception:
                                try:
                                    parsed = _dt.datetime.utcfromtimestamp(float(ev_ts) / 1000.0).replace(tzinfo=_dt.timezone.utc)
                                except Exception:
                                    parsed = None
                            if parsed is None:
                                continue
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
                            if parsed < start_ts or parsed >= end_ts:
                                continue
                            msg = ev.get('msg') or {}
                            o = msg.get('o') if isinstance(msg, dict) and 'o' in msg else msg
                            s = (o.get('s') or o.get('symbol') or '')
                            if not s:
                                continue
                            if str(s).upper().replace('/', '').replace('-', '') != norm:
                                continue
                            qty = 0.0
                            price = 0.0
                            try:
                                qty = float(o.get('q') or o.get('qty') or o.get('z') or 0.0)
                            except Exception:
                                qty = 0.0
                            try:
                                price = float(o.get('ap') or o.get('p') or 0.0)
                            except Exception:
                                price = 0.0
                            quote = qty * price
                            side = (o.get('S') or o.get('side') or '')
                            s_up = str(side).upper()
                            if s_up.startswith('S') or s_up == 'SELL':
                                # SELL -> treat as long liquidation
                                long_totals[sym] += quote
                            elif s_up.startswith('B') or s_up == 'BUY':
                                short_totals[sym] += quote
                        except Exception:
                            continue
                except Exception:
                    continue
        # Build ranked lists
        def build_ranking(dct):
            items = [(sym, round(vol, 6)) for sym, vol in dct.items()]
            items.sort(key=lambda x: x[1], reverse=True)
            return [{'symbol': sym, 'quote_usd': vol} for sym, vol in items]

        hot_rankings = {
            'longs': build_ranking(long_totals),
            'shorts': build_ranking(short_totals),
        }
    except Exception:
        hot_rankings = {'longs': [], 'shorts': []}

    return {'by_minute': aggregates, 'hot_by_minute': hot_by_minute, 'hot_rankings': hot_rankings}



@app.get('/debug/hotcoins_agg')
async def debug_hotcoins_agg():
    """Return metadata about the hotcoins aggregation cache for debugging.

    Response:
    { last_ts, last_hot_list_sample, minutes_window, cached_minutes_count }
    """
    try:
        async with _hot_by_minute_lock:
            cached_minutes = list(_hot_by_minute_cache.keys()) if _hot_by_minute_cache else []
            sample = {}
            # include up to 5 minutes of data and at most 10 symbols each
            for mi in cached_minutes[:5]:
                syms = list((_hot_by_minute_cache.get(mi) or {}).keys())[:10]
                sample[mi] = {s: _hot_by_minute_cache[mi][s] for s in syms}
            return {
                'last_ts': _hotcoins_agg_last_ts,
                'last_hot_list_sample': _hotcoins_agg_last_hot_list[:50] if _hotcoins_agg_last_hot_list else [],
                'minutes_window': _hot_by_minute_window_min,
                'cached_minutes_count': len(cached_minutes),
                'sample': sample,
            }
    except Exception:
        return {'error': 'failed to read hotcoins cache'}

# -----------------------------------------------------------------------------
# HTTP endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/debug/ip")
async def debug_ip(request: Request):
    """Get Railway's public IP address"""
    try:
        # Try to get IP from various sources
        import requests
        
        # Get IP from external service
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        external_ip = response.json().get('ip', 'Unknown')
        
        # Get more info about the IP
        try:
            info_response = requests.get(f'https://ipapi.co/{external_ip}/json/', timeout=5)
            ip_info = info_response.json()
        except:
            ip_info = {}
        
        return {
            'ip': external_ip,
            'country': ip_info.get('country_name', 'Unknown'),
            'city': ip_info.get('city', 'Unknown'),
            'org': ip_info.get('org', 'Unknown'),
            'timezone': ip_info.get('timezone', 'Unknown')
        }
    except Exception as e:
        return {'error': str(e), 'ip': 'Unknown'}

@app.get("/api/debug/config")
async def debug_config():
    """Check if API keys are configured (without exposing full keys)"""
    api_key = os.environ.get('BINANCE_API_KEY', '')
    api_secret = os.environ.get('BINANCE_API_SECRET', '')
    live_orders = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0')
    
    return {
        'has_api_key': bool(api_key and len(api_key) > 10),
        'has_api_secret': bool(api_secret and len(api_secret) > 10),
        'api_key_preview': api_key[:10] + '...' if len(api_key) > 10 else 'Not Set',
        'api_secret_preview': api_secret[:10] + '...' if len(api_secret) > 10 else 'Not Set',
        'live_orders_enabled': live_orders == '1',
        'live_orders_flag': live_orders
    }

@app.get("/api/debug/test-binance")
async def debug_test_binance():
    """Test Binance API connection"""
    try:
        import ccxt
        
        api_key = os.environ.get('BINANCE_API_KEY', '')
        api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        if not api_key or not api_secret:
            return {
                'success': False,
                'error': 'API credentials not configured'
            }
        
        # Try to connect to Binance
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })
        
        # Test connection
        balance = exchange.fetch_balance()
        
        # Get non-zero balances
        non_zero = {k: v for k, v in balance['total'].items() if v > 0}
        
        return {
            'success': True,
            'can_trade': True,
            'futures_enabled': True,
            'balances': list(non_zero.keys())[:10]
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

@app.get("/logs/raw")
async def get_logs_raw():
    return server_logs[-200:]

@app.get('/debug/ccxt_status')
async def debug_ccxt_status():
    cache_keys = list(_ccxt_instances.keys())
    recent = [e for e in server_logs[-200:] if isinstance(e, dict) and ('ccxt.' in e.get('text', '') or 'scan:' in e.get('text','') or 'initial scan' in e.get('text',''))]
    return {'ccxt_cached_keys': cache_keys, 'recent_ccxt_logs': recent}

@app.get('/debug/feeder_status')
async def debug_feeder_status():
    try:
        from .exchanges.ws_feed_manager import list_feeders
    except Exception:
        return {'error': 'ws_feed_manager import failed'}
    # (balance endpoints are registered at module level below)

    try:
        feeds = list_feeders()
        out = []
        for name, inst in feeds.items():
            try:
                if hasattr(inst, 'get_status'):
                    try:
                        st = inst.get_status() or {}
                        # normalize feeder name
                        if isinstance(st, dict) and 'feeder' not in st:
                            st['feeder'] = name
                        out.append(st)
                        continue
                    except Exception:
                        pass
                # fallback summaries for older feeders
                try:
                    books = getattr(inst, '_books', {}) or {}
                    last_ts = getattr(inst, '_ts', None)
                    keys = list(books.keys())[:50]
                    out.append({'feeder': name, 'status': 'ok', 'symbol_count': len(books), 'symbols_sample': keys, 'last_update_ts': last_ts})
                except Exception:
                    out.append({'feeder': name, 'status': 'unknown'})
            except Exception:
                out.append({'feeder': name, 'status': 'error'})

        # If no feeders are registered, return a helpful default
        if not out:
            return {'status': 'no_feeders_registered'}
        return out
    except Exception as e:
        return {'error': str(e)}


@app.get('/api/tickers/binance')
async def api_tickers_binance():
    try:
        inst = await _get_ccxt_instance('binance', None, None)
        if inst is None:
            return {'error': 'ccxt/binance instance unavailable'}, 500
        def _get():
            try:
                if hasattr(inst, 'get_tickers'):
                    return inst.get_tickers()
                if hasattr(inst, 'fetch_tickers'):
                    return inst.fetch_tickers()
                return {}
            except Exception:
                return {}
        tk = await asyncio.to_thread(_get)
        # normalize to symbol->price
        out = {}
        for k, v in (tk or {}).items():
            try:
                price = None
                if isinstance(v, dict):
                    for field in ('last', 'close', 'price'):
                        if field in v and v.get(field) is not None:
                            price = float(v.get(field))
                            break
                elif isinstance(v, (int, float)):
                    price = float(v)
                if price is not None:
                    out[str(k).upper()] = price
            except Exception:
                continue
        return out
    except Exception as e:
        return {'error': str(e)}


@app.get('/api/tickers/mexc')
async def api_tickers_mexc():
    try:
        inst = await _get_ccxt_instance('mexc', None, None)
        if inst is None:
            return {'error': 'ccxt/mexc instance unavailable'}, 500
        def _get():
            try:
                if hasattr(inst, 'get_tickers'):
                    return inst.get_tickers()
                if hasattr(inst, 'fetch_tickers'):
                    return inst.fetch_tickers()
                return {}
            except Exception:
                return {}
        tk = await asyncio.to_thread(_get)
        out = {}
        for k, v in (tk or {}).items():
            try:
                price = None
                if isinstance(v, dict):
                    for field in ('last', 'close', 'price'):
                        if field in v and v.get(field) is not None:
                            price = float(v.get(field))
                            break
                elif isinstance(v, (int, float)):
                    price = float(v)
                if price is not None:
                    out[str(k).upper()] = price
            except Exception:
                continue
        return out
    except Exception as e:
        return {'error': str(e)}


@app.get('/api/balances/binance')
async def api_balances_binance():
    """Return a simple map of balances from Binance (requires BINANCE_API_KEY/SECRET env vars).

    Response: { asset: { free, locked } }
    """
    try:
        key = (os.environ.get('BINANCE_API_KEY') or '').strip()
        secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
        if not key or not secret:
            return {'error': 'BINANCE_API_KEY/SECRET not configured'}, 400
        inst = await _get_ccxt_instance('binance', key, secret)
        if inst is None:
            return {'error': 'ccxt/binance instance unavailable'}, 500
        # run fetch_balance in thread
        def _fetch():
            try:
                return inst.client.fetch_balance()
            except Exception:
                return None
        bal = await asyncio.to_thread(_fetch)
        if not bal:
            return {'error': 'failed to fetch balances'}, 500
        # convert to simple map
        out = {}
        for k, v in (bal.get('total') or {}).items():
            try:
                free = (bal.get('free') or {}).get(k) if isinstance(bal.get('free'), dict) else None
                locked = (bal.get('locked') or {}).get(k) if isinstance(bal.get('locked'), dict) else None
                out[k] = {'free': free or 0.0, 'locked': locked or 0.0}
            except Exception:
                continue
        return out
    except Exception as e:
        return {'error': str(e)}


@app.get('/api/hotcoins/vol_index')
async def api_hotcoins_vol_index(limit: int = 50):
    """Return the latest daily volatility index for hotcoins.

    This endpoint prefers to read the most recent snapshot from the history CSV
    `var/hotcoins_vol_history.csv` (if present) and return the latest entries
    per symbol. If history is missing, it will attempt to compute a fresh snapshot
    by invoking the internal hotcoins finder and fetching daily klines.
    """
    try:
        history_path = os.path.join(ROOT, 'var', 'hotcoins_vol_history.csv')
        out = []
        if os.path.exists(history_path):
            # read CSV and pick the latest timestamp for each symbol
            import csv
            latest_for_symbol = {}
            with open(history_path, 'r', newline='', encoding='utf-8') as fh:
                rdr = csv.DictReader(fh)
                for row in rdr:
                    try:
                        ts = row.get('ts')
                        sym = row.get('symbol')
                        if not sym:
                            continue
                        # keep the latest by lexicographic ISO ts
                        prev = latest_for_symbol.get(sym)
                        if prev is None or (ts and prev.get('ts', '') < ts):
                            latest_for_symbol[sym] = {
                                'ts': ts,
                                'symbol': sym,
                                'last': float(row.get('last') or 0),
                                'volatility': float(row.get('volatility') or 0),
                                'ewma_volatility': float(row.get('ewma_volatility') or 0),
                                'vol_percentile': float(row.get('vol_percentile') or 0),
                                'mover': float(row.get('mover') or 0),
                            }
                    except Exception:
                        continue
            # sort by volatility desc and limit
            out = sorted(list(latest_for_symbol.values()), key=lambda x: x.get('volatility', 0.0), reverse=True)[:limit]
            # If history contains enough items, return immediately.
            if len(out) >= limit:
                return {'ts': out[0]['ts'] if out else None, 'items': out}

            # Otherwise, compute a fresh snapshot for current hotcoins and
            # merge computed rows with history so we can return up to `limit` items.
            try:
                from src.arbitrage.hotcoins import find_hot_coins
            except Exception:
                find_hot_coins = None

            # Prefer the in-memory canonical hotcoins aggregation maintained by
            # the hotcoins aggregator loop. This ensures we compute vols for the
            # same list the UI shows instead of falling back to Binance top-by-volume.
            try:
                hot_candidates = []
                if _hotcoins_agg_last_hot_list and len(_hotcoins_agg_last_hot_list) > 0:
                    hot_candidates = list(_hotcoins_agg_last_hot_list)
                elif callable(find_hot_coins):
                    try:
                        hot_candidates = await asyncio.to_thread(find_hot_coins, None, limit) or []
                    except Exception:
                        hot_candidates = []
                else:
                    hot_candidates = []
            except Exception:
                hot_candidates = []

            # local helpers (same as fallback block below)
            def fetch_klines_local(symbol: str, interval: str = '1d', limit: int = 30):
                """Try several public REST endpoints (Binance, KuCoin, Gate) and
                return the first successful klines/candles array.
                """
                from urllib import request as _r
                import json as _json

                # Normalize forms
                s_noslash = symbol.replace('/', '').replace('-', '').replace('_', '')
                s_dash = symbol.replace('/', '-').replace('_', '-')
                s_under = symbol.replace('/', '_').replace('-', '_')

                # 1) Binance
                try:
                    url_b = 'https://api.binance.com/api/v3/klines?symbol=' + s_noslash + '&interval=' + interval + '&limit=' + str(limit)
                    req = _r.Request(url_b, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        if isinstance(data, list) and len(data) > 0:
                            return data
                except Exception:
                    pass

                # 2) KuCoin (candles) - KuCoin uses types like '1day' for daily
                try:
                    ktype = '1day' if interval == '1d' else ('1hour' if interval == '1h' else interval)
                    url_k = 'https://api.kucoin.com/api/v1/market/candles?symbol=' + s_dash + '&type=' + ktype + '&limit=' + str(limit)
                    req = _r.Request(url_k, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        # KuCoin returns [ [time, open, close, high, low, volume], ... ] or {code:.., data: [...]}
                        if isinstance(data, dict) and data.get('code') == '200' and isinstance(data.get('data'), list):
                            rows = data.get('data')
                            if rows:
                                return rows
                        if isinstance(data, list) and data:
                            return data
                except Exception:
                    pass

                # 3) Gate.io (candles) - interval mapping: 1d -> 86400
                try:
                    period = '86400' if interval == '1d' else ('3600' if interval == '1h' else interval)
                    url_g = 'https://api.gateio.ws/api/v4/spot/candles?currency_pair=' + s_under + '&interval=' + period + '&limit=' + str(limit)
                    req = _r.Request(url_g, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        if isinstance(data, list) and len(data) > 0:
                            return data
                except Exception:
                    pass

                return []

            def close_prices_local(klines):
                outp = []
                for k in klines:
                    try:
                        outp.append(float(k[4]))
                    except Exception:
                        continue
                return outp

            def realized_vol_local(prices, periods_per_year):
                import math as _math, statistics as _stats
                if not prices or len(prices) < 2:
                    return None
                rets = []
                for i in range(1, len(prices)):
                    p0 = prices[i - 1]
                    p1 = prices[i]
                    if p0 <= 0 or p1 <= 0:
                        continue
                    rets.append(_math.log(p1 / p0))
                if not rets:
                    return None
                sd = _stats.pstdev(rets)
                return sd * _math.sqrt(365.0)

            # Compute only for hot candidates not already present in history
            def norm_sym(s):
                try:
                    return (str(s or '')).upper().replace('/', '').replace('-', '').replace('_', '')
                except Exception:
                    return ''

            existing = set(norm_sym(r.get('symbol')) for r in out)
            computed_rows = []
            for it in hot_candidates:
                # extract symbol from either dict or string entry
                sym = None
                try:
                    if isinstance(it, dict):
                        sym = it.get('symbol') or (str(it.get('base') or '') + (str(it.get('quote') or '') or 'USDT'))
                    else:
                        sym = str(it)
                except Exception:
                    sym = None
                if not sym:
                    continue
                ns = norm_sym(sym)
                if not ns or ns in existing:
                    continue
                kl = fetch_klines_local(sym, interval='1d', limit=30)
                prices = close_prices_local(kl)
                vol = realized_vol_local(prices, 365.0)
                last = prices[-1] if prices else None
                if vol is None:
                    # don't include unsuccessful computations
                    continue
                computed_rows.append({'symbol': sym, 'last': last, 'volatility': vol})
                existing.add(ns)
                if len(computed_rows) >= limit:
                    break
            computed_rows = sorted([r for r in computed_rows if r.get('volatility') is not None], key=lambda x: x.get('volatility', 0.0), reverse=True)[:limit]

            # merge: prefer computed rows first, then historical rows not present
            def norm_sym(s):
                try:
                    return (str(s or '')).upper().replace('/', '').replace('-', '').replace('_', '')
                except Exception:
                    return ''

            seen = set()
            combined = []
            for r in computed_rows:
                ns = norm_sym(r.get('symbol'))
                if not ns or ns in seen:
                    continue
                seen.add(ns)
                combined.append(r)
            for r in out:
                ns = norm_sym(r.get('symbol'))
                if not ns or ns in seen:
                    continue
                seen.add(ns)
                combined.append(r)
                if len(combined) >= limit:
                    break

            return {'ts': out[0]['ts'] if out else None, 'items': combined}

        # fallback: compute on-demand using hotcoins finder and daily klines
        try:
            from src.arbitrage.hotcoins import find_hot_coins
            items = await asyncio.to_thread(find_hot_coins, None, limit)
        except Exception:
            items = []
        # reuse the volatility tool (local) to compute daily vols
        try:
            # import the helper functions from tools by reading the module file
            # to avoid circular package imports we'll implement a small local logic here
            def fetch_klines_local(symbol: str, interval: str = '1d', limit: int = 30):
                """Try several public REST endpoints (Binance, KuCoin, Gate) and
                return the first successful klines/candles array.
                """
                from urllib import request as _r
                import json as _json

                # Normalize forms
                s_noslash = symbol.replace('/', '').replace('-', '').replace('_', '')
                s_dash = symbol.replace('/', '-').replace('_', '-')
                s_under = symbol.replace('/', '_').replace('-', '_')

                # 1) Binance
                try:
                    url_b = 'https://api.binance.com/api/v3/klines?symbol=' + s_noslash + '&interval=' + interval + '&limit=' + str(limit)
                    req = _r.Request(url_b, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        if isinstance(data, list) and len(data) > 0:
                            return data
                except Exception:
                    pass

                # 2) KuCoin (candles) - KuCoin uses types like '1day' for daily
                try:
                    ktype = '1day' if interval == '1d' else ('1hour' if interval == '1h' else interval)
                    url_k = 'https://api.kucoin.com/api/v1/market/candles?symbol=' + s_dash + '&type=' + ktype + '&limit=' + str(limit)
                    req = _r.Request(url_k, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        # KuCoin returns [ [time, open, close, high, low, volume], ... ] or {code:.., data: [...]}
                        if isinstance(data, dict) and data.get('code') == '200' and isinstance(data.get('data'), list):
                            rows = data.get('data')
                            if rows:
                                return rows
                        if isinstance(data, list) and data:
                            return data
                except Exception:
                    pass

                # 3) Gate.io (candles) - interval mapping: 1d -> 86400
                try:
                    period = '86400' if interval == '1d' else ('3600' if interval == '1h' else interval)
                    url_g = 'https://api.gateio.ws/api/v4/spot/candles?currency_pair=' + s_under + '&interval=' + period + '&limit=' + str(limit)
                    req = _r.Request(url_g, headers={'User-Agent': 'arb-vol-index/1.0'})
                    with _r.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode('utf-8'))
                        if isinstance(data, list) and len(data) > 0:
                            return data
                except Exception:
                    pass

                return []

            def close_prices_local(klines):
                outp = []
                for k in klines:
                    try:
                        outp.append(float(k[4]))
                    except Exception:
                        continue
                return outp

            def realized_vol_local(prices, periods_per_year):
                import math as _math, statistics as _stats
                if not prices or len(prices) < 2:
                    return None
                rets = []
                for i in range(1, len(prices)):
                    p0 = prices[i - 1]
                    p1 = prices[i]
                    if p0 <= 0 or p1 <= 0:
                        continue
                    rets.append(_math.log(p1 / p0))
                if not rets:
                    return None
                sd = _stats.pstdev(rets)
                return sd * _math.sqrt(365.0)

            rows = []
            for it in items:
                sym = it.get('symbol') if isinstance(it, dict) else None
                if not sym:
                    continue
                kl = fetch_klines_local(sym, interval='1d', limit=30)
                prices = close_prices_local(kl)
                vol = realized_vol_local(prices, 365.0)
                last = prices[-1] if prices else None
                rows.append({'symbol': sym, 'last': last, 'volatility': vol})
            rows = sorted([r for r in rows if r.get('volatility') is not None], key=lambda x: x.get('volatility', 0.0), reverse=True)[:limit]
            return {'ts': None, 'items': rows}
        except Exception as e:
            return {'error': str(e)}
    except Exception as e:
        return {'error': str(e)}


@app.get('/api/balances/mexc')
async def api_balances_mexc():
    """Return balances from MEXC using CCXT if available.
    """
    try:
        key = (os.environ.get('MEXC_API_KEY') or '').strip()
        secret = (os.environ.get('MEXC_API_SECRET') or '').strip()
        if not key or not secret:
            return {'error': 'MEXC_API_KEY/SECRET not configured'}, 400
        inst = await _get_ccxt_instance('mexc', key, secret)
        if inst is None:
            return {'error': 'ccxt/mexc instance unavailable'}, 500
        def _fetch():
            try:
                return inst.client.fetch_balance()
            except Exception:
                return None
        bal = await asyncio.to_thread(_fetch)
        if not bal:
            return {'error': 'failed to fetch balances'}, 500
        out = {}
        for k, v in (bal.get('total') or {}).items():
            try:
                free = (bal.get('free') or {}).get(k) if isinstance(bal.get('free'), dict) else None
                locked = (bal.get('locked') or {}).get(k) if isinstance(bal.get('locked'), dict) else None
                out[k] = {'free': free or 0.0, 'locked': locked or 0.0}
            except Exception:
                continue
        return out
    except Exception as e:
        return {'error': str(e)}

@app.get('/debug/feeder_depths')
async def debug_feeder_depths(feeder_name: str = 'binance', levels: int = 5):
    try:
        from .exchanges.ws_feed_manager import get_feeder
    except Exception:
        return {'error': 'ws_feed_manager import failed'}
    try:
        f = get_feeder(feeder_name)
        if not f:
            return {'feeder': feeder_name, 'status': 'not_registered'}
        depths: dict = {}
        prices: dict = {}
        last_ts = getattr(f, 'last_update_ts', None) or getattr(f, '_ts', None)

        # Prefer feeder-provided status helper if available
        try:
            if hasattr(f, 'get_status'):
                try:
                    st = f.get_status() or {}
                    # Accept several shapes from feeders: depths, book_tickers, bids (simple map), or tickers
                    d = st.get('depths') or st.get('book_tickers') or st.get('bids') or st.get('tickers') or {}
                    ts = st.get('last_update_ts') if st.get('last_update_ts') is not None else last_ts
                    # If the status returned a simple 'bids' map, numeric entries should be treated as prices
                    st_has_bids_map = isinstance(st.get('bids'), dict)
                    if isinstance(d, dict) and d:
                        # compute a price marker for each symbol. Prefer book top-of-book
                        # mid price when available, otherwise fall back to tickers.last.
                        for sym, val in d.items():
                            try:
                                price = None
                                # If the feeder returned a book-like object, compute mid price
                                if isinstance(val, dict):
                                    bid = val.get('bid') or val.get('b') or val.get('highest_bid') or val.get('best_bid')
                                    ask = val.get('ask') or val.get('a') or val.get('lowest_ask') or val.get('best_ask')
                                    if bid is not None or ask is not None:
                                        try:
                                            b = float(bid) if bid is not None else None
                                            a = float(ask) if ask is not None else None
                                            if b is not None and a is not None:
                                                price = (b + a) / 2.0
                                            elif b is not None:
                                                price = b
                                            elif a is not None:
                                                price = a
                                        except Exception:
                                            price = None
                                    elif val.get('last') is not None:
                                        try:
                                            price = float(val.get('last'))
                                        except Exception:
                                            price = None
                                # If feeder returned a numeric value:
                                # - if the original status included a 'bids' map, treat numeric as price
                                # - otherwise attempt to find a real price from tickers or book_tickers
                                elif isinstance(val, (int, float)):
                                    if st_has_bids_map:
                                        try:
                                            price = float(val)
                                        except Exception:
                                            price = None
                                    else:
                                        tk_map = st.get('tickers') or {}
                                        tkinfo = tk_map.get(sym) or tk_map.get(sym.replace('/', '_')) if isinstance(tk_map, dict) else None
                                        if isinstance(tkinfo, dict) and tkinfo.get('last') is not None:
                                            try:
                                                price = float(tkinfo.get('last'))
                                            except Exception:
                                                price = None

                                # Fallback: try feeder.get_book_tickers() and get_tickers()
                                if price is None:
                                    try:
                                        if hasattr(f, 'get_book_tickers'):
                                            bks = f.get_book_tickers() or {}
                                            bv = bks.get(sym) or bks.get(sym.replace('/', '_')) or bks.get(sym.replace('_', '/'))
                                            if isinstance(bv, dict):
                                                bb = bv.get('bid') or bv.get('b')
                                                aa = bv.get('ask') or bv.get('a')
                                                try:
                                                    bbn = float(bb) if bb is not None else None
                                                    aan = float(aa) if aa is not None else None
                                                    if bbn is not None and aan is not None:
                                                        price = (bbn + aan) / 2.0
                                                    elif bbn is not None:
                                                        price = bbn
                                                    elif aan is not None:
                                                        price = aan
                                                except Exception:
                                                    price = None
                                        if price is None and hasattr(f, 'get_tickers'):
                                            tks = f.get_tickers() or {}
                                            tv = tks.get(sym) or tks.get(sym.replace('/', '_')) or tks.get(sym.replace('_', '/'))
                                            if isinstance(tv, dict) and tv.get('last') is not None:
                                                try:
                                                    price = float(tv.get('last'))
                                                except Exception:
                                                    price = None
                                    except Exception:
                                        pass

                                # store computed price separately
                                prices[sym] = float(price) if price is not None else None
                                # preserve depths: if original val is numeric, treat it as depth; otherwise leave depth unknown
                                if isinstance(val, (int, float)):
                                    try:
                                        depths[sym] = float(val)
                                    except Exception:
                                        depths[sym] = None
                                else:
                                    depths[sym] = depths.get(sym, None)
                            except Exception:
                                depths[sym] = None
                                prices[sym] = None
                        return {'feeder': feeder_name, 'status': st.get('status', 'ok'), 'depths': depths, 'prices': prices, 'last_update_ts': ts}
                except Exception:
                    pass

        except Exception:
            pass

        # Next try feeder.get_book_tickers() which GateDepthFeeder exposes
        try:
            if hasattr(f, 'get_book_tickers'):
                try:
                    bks = f.get_book_tickers() or {}
                    if isinstance(bks, dict) and bks:
                        for sym, v in list(bks.items())[:1000]:
                            try:
                                bid = v.get('bid') if isinstance(v, dict) else None
                                ask = v.get('ask') if isinstance(v, dict) else None
                                bid_sz = v.get('bid_sz') if isinstance(v, dict) else None
                                ask_sz = v.get('ask_sz') if isinstance(v, dict) else None
                                # approximate depth by summing top-level size*price when available
                                ssum = 0.0
                                if bid is not None and bid_sz is not None:
                                    try:
                                        ssum += float(bid) * float(bid_sz)
                                    except Exception:
                                        pass
                                if ask is not None and ask_sz is not None:
                                    try:
                                        ssum += float(ask) * float(ask_sz)
                                    except Exception:
                                        pass
                                depths[sym] = ssum if ssum > 0 else None
                                # compute mid price when available
                                try:
                                    if bid is not None or ask is not None:
                                        bvn = float(bid) if bid is not None else None
                                        avn = float(ask) if ask is not None else None
                                        if bvn is not None and avn is not None:
                                            prices[sym] = (bvn + avn) / 2.0
                                        elif bvn is not None:
                                            prices[sym] = bvn
                                        elif avn is not None:
                                            prices[sym] = avn
                                        else:
                                            prices[sym] = None
                                except Exception:
                                    prices[sym] = None
                            except Exception:
                                continue
                        return {'feeder': feeder_name, 'status': 'ok', 'depths': depths, 'prices': prices, 'last_update_ts': last_ts}
                except Exception:
                    pass
        except Exception:
            pass

        # Fallback: try internal _book_tickers or _books structures
        try:
            books = getattr(f, '_book_tickers', None) or getattr(f, '_books', None) or {}
            if isinstance(books, dict) and books:
                for sym, data in list(books.items())[:1000]:
                    try:
                        # data may be dict with asks/bids or price/size pairs
                        asks = data.get('asks', [])[:levels] if isinstance(data, dict) else []
                        bids = data.get('bids', [])[:levels] if isinstance(data, dict) else []
                        ssum = 0.0
                        for p, q in (asks + bids):
                            try:
                                ssum += float(p) * float(q)
                            except Exception:
                                continue
                        depths[sym] = ssum
                        # derive a top-of-book price from asks/bids if available
                        try:
                            top_bid = bids[0][0] if bids and len(bids[0]) > 0 else None
                            top_ask = asks[0][0] if asks and len(asks[0]) > 0 else None
                            if top_bid is not None or top_ask is not None:
                                bvn = float(top_bid) if top_bid is not None else None
                                avn = float(top_ask) if top_ask is not None else None
                                if bvn is not None and avn is not None:
                                    prices[sym] = (bvn + avn) / 2.0
                                elif bvn is not None:
                                    prices[sym] = bvn
                                elif avn is not None:
                                    prices[sym] = avn
                                else:
                                    prices[sym] = None
                        except Exception:
                            prices[sym] = None
                    except Exception:
                        continue
                return {'feeder': feeder_name, 'status': 'ok', 'depths': depths, 'prices': prices, 'last_update_ts': last_ts}
        except Exception:
            pass

        syms = getattr(f, 'symbols', None) or getattr(f, '_symbols', None) or []
        if syms and hasattr(f, 'get_order_book'):
            for sym in syms[:1000]:
                try:
                    ob = f.get_order_book(sym, depth=levels) or {}
                    asks = ob.get('asks', [])[:levels]
                    bids = ob.get('bids', [])[:levels]
                    ssum = 0.0
                    for p, q in (asks + bids):
                        try:
                            ssum += float(p) * float(q)
                        except Exception:
                            continue
                    depths[sym] = ssum
                    # derive mid price from top levels if available
                    try:
                        top_bid = bids[0][0] if bids and len(bids[0]) > 0 else None
                        top_ask = asks[0][0] if asks and len(asks[0]) > 0 else None
                        if top_bid is not None or top_ask is not None:
                            bvn = float(top_bid) if top_bid is not None else None
                            avn = float(top_ask) if top_ask is not None else None
                            if bvn is not None and avn is not None:
                                prices[sym] = (bvn + avn) / 2.0
                            elif bvn is not None:
                                prices[sym] = bvn
                            elif avn is not None:
                                prices[sym] = avn
                            else:
                                prices[sym] = None
                    except Exception:
                        prices[sym] = None
                except Exception:
                    continue
            return {'feeder': feeder_name, 'status': 'ok', 'depths': depths, 'prices': prices, 'last_update_ts': last_ts}

        # Fallback: if no orderbook/book_ticker data but the feeder provides
        # tickers (recent last prices), expose them as simple depth-like
        # price markers so the UI can show a price column for the feeder.
        try:
            if hasattr(f, 'get_tickers'):
                try:
                    tks = f.get_tickers() or {}
                    if isinstance(tks, dict) and tks:
                        for sym, v in tks.items():
                            try:
                                if isinstance(v, dict):
                                    last = v.get('last')
                                else:
                                    last = None
                                prices[sym] = float(last) if last is not None else None
                                depths[sym] = depths.get(sym, None)
                            except Exception:
                                depths[sym] = depths.get(sym, None)
                                prices[sym] = prices.get(sym, None)
                        return {'feeder': feeder_name, 'status': 'ok', 'depths': depths, 'prices': prices, 'last_update_ts': last_ts}
                except Exception:
                    pass
        except Exception:
            pass

        return {'feeder': feeder_name, 'status': 'no_orderbook_data', 'last_update_ts': last_ts}
    except Exception as e:
        return {'error': str(e)}

@app.get("/file_opportunities")
async def file_opportunities(max_profit_pct: float = 10.0, enrich: bool = False):
    raise HTTPException(status_code=404, detail='file_opportunities endpoint disabled')

# -----------------------------------------------------------------------------
# Execute endpoint
# -----------------------------------------------------------------------------
@app.post("/execute")
async def execute_trade(request: Request):
    """Execute (or dry-run) an opportunity."""
    api_key = request.headers.get("x-api-key")
    expected = os.environ.get("ARB_API_KEY", "demo-key")
    if api_key != expected:
        raise HTTPException(status_code=401, detail="invalid API key")

    body = await request.json()
    opp_data = body.get("opportunity")
    if not opp_data:
        raise HTTPException(status_code=400, detail="missing opportunity")

    opp = Opportunity(
        buy_exchange=opp_data.get("buy_exchange"),
        sell_exchange=opp_data.get("sell_exchange"),
        symbol=opp_data.get("symbol"),
        buy_price=float(opp_data.get("buy_price", 0)),
        sell_price=float(opp_data.get("sell_price", 0)),
        profit_pct=float(opp_data.get("profit_pct", 0)),
    )

    amount = float(body.get("amount", 0.0))
    dry_run = bool(body.get("dry_run", True))
    allow_live = bool(body.get("allow_live", False))

    ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
    ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
    ex3 = MockExchange("DEX-X", {"BTC-USD": 50050.0})
    executor = Executor([ex1, ex2, ex3])

    is_dex = (opp.buy_exchange and opp.buy_exchange.startswith('DEX')) or (opp.sell_exchange and opp.sell_exchange.startswith('DEX'))
    if is_dex and not dry_run:
        if not allow_live or os.environ.get('ALLOW_LIVE_ONCHAIN', '0') != '1':
            raise HTTPException(status_code=403, detail='live on-chain DEX trades are disabled on this server')

    result = executor.execute(opp, amount=amount, dry_run=dry_run)
    if isinstance(result.get("opportunity"), Opportunity):
        result["opportunity"] = result["opportunity"].__dict__
    try:
        from datetime import datetime
        server_logs.append({"ts": datetime.utcnow().isoformat(), "text": f"execute: {json.dumps(result)}"})
    except Exception:
        pass
    return result


# -----------------------------------------------------------------------------
# Liquidation listener control endpoints
# -----------------------------------------------------------------------------
_listener_process = None
_listener_status = {'running': False, 'pid': None, 'started_at': None}

@app.post('/api/liquidations/start-listener')
async def start_liquidation_listener():
    """Start the Binance liquidation listener script in the background."""
    global _listener_process, _listener_status
    
    if _listener_status['running']:
        return {'status': 'already_running', 'pid': _listener_status['pid']}
    
    try:
        import subprocess
        import sys
        
        # Path to the listener script
        script_path = os.path.join(ROOT, 'tools', 'binance_liquidation_listener.py')
        if not os.path.exists(script_path):
            raise HTTPException(status_code=404, detail=f'Listener script not found at {script_path}')
        
        # Get the backend URL for forwarding
        forward_url = 'http://127.0.0.1:8000/liquidations/ingest'
        
        # Start the listener process with forwarding enabled
        _listener_process = subprocess.Popen(
            [sys.executable, script_path, 
             '--stream', '!forceOrder@arr',
             '--duration', '86400',  # Run for 24 hours
             '--forward', forward_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        _listener_status = {
            'running': True,
            'pid': _listener_process.pid,
            'started_at': _dt.datetime.utcnow().isoformat()
        }
        
        return {
            'status': 'started',
            'pid': _listener_process.pid,
            'started_at': _listener_status['started_at']
        }
        
    except Exception as e:
        _listener_status['running'] = False
        raise HTTPException(status_code=500, detail=f'Failed to start listener: {str(e)}')


@app.post('/api/liquidations/stop-listener')
async def stop_liquidation_listener():
    """Stop the running liquidation listener."""
    global _listener_process, _listener_status
    
    if not _listener_status['running'] or _listener_process is None:
        return {'status': 'not_running'}
    
    try:
        _listener_process.terminate()
        try:
            _listener_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _listener_process.kill()
            _listener_process.wait()
        
        _listener_status = {'running': False, 'pid': None, 'started_at': None}
        _listener_process = None
        
        return {'status': 'stopped'}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to stop listener: {str(e)}')


@app.get('/api/liquidations/listener-status')
async def liquidation_listener_status():
    """Get the current status of the liquidation listener."""
    global _listener_process, _listener_status
    
    # Check if process is still alive
    if _listener_status['running'] and _listener_process:
        poll = _listener_process.poll()
        if poll is not None:
            # Process has exited
            _listener_status['running'] = False
            _listener_status['pid'] = None
    
    return _listener_status
