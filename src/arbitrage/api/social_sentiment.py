"""
Social sentiment endpoint using LunarCrush API
Updated: 2025-10-10
"""
import os
import logging
import asyncio
import time
from typing import Optional, Dict, Any
import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# Get LunarCrush API key from environment
LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")
logger.info(f"[SOCIAL_SENTIMENT] LunarCrush API key loaded: {len(LUNARCRUSH_API_KEY) > 0} (length: {len(LUNARCRUSH_API_KEY)})")

# Cache for scanner results (3-minute TTL)
_scanner_cache = {
    'volume_surges': {'data': None, 'timestamp': 0},
    'breakouts': {'data': None, 'timestamp': 0},
    'funding': {'data': None, 'timestamp': 0}
}
CACHE_TTL = 300  # 5 minutes in seconds (matches frontend auto-refresh)

# Rate limiting for LunarCrush API
_last_api_call = 0
_api_call_delay = 0.5  # 500ms between calls (120 calls per minute max)
_marketcap_cache = {}  # Cache market cap data for 5 minutes
_marketcap_cache_ttl = 300


def get_lunarcrush_symbol(symbol: str) -> str:
    """
    Map trading symbols to LunarCrush symbols (usually just remove USDT/BUSD suffix)
    """
    # Remove common suffixes
    base_symbol = symbol.replace('USDT', '').replace('BUSD', '').replace('USD', '').replace('PERP', '')
    return base_symbol.upper()


async def fetch_lunarcrush_data(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch social sentiment data from LunarCrush API (async)
    Uses both /coins and /topic endpoints for comprehensive data
    """
    global _last_api_call, _marketcap_cache
    
    if not LUNARCRUSH_API_KEY:
        logger.warning("LunarCrush API key not configured")
        return None
    
    # Check cache first
    cache_key = f"mc_{symbol}"
    if cache_key in _marketcap_cache:
        cached_data, timestamp = _marketcap_cache[cache_key]
        if time.time() - timestamp < _marketcap_cache_ttl:
            logger.debug(f"Using cached data for {symbol}")
            return cached_data
    
    # Rate limiting
    now = time.time()
    time_since_last_call = now - _last_api_call
    if time_since_last_call < _api_call_delay:
        await asyncio.sleep(_api_call_delay - time_since_last_call)
    _last_api_call = time.time()
    
    try:
        headers = {
            "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get basic coin data (galaxy score, alt rank)
            coin_url = f"https://lunarcrush.com/api4/public/coins/{symbol}/v1"
            
            # Get social/topic data (tweets, sentiment, interactions)
            topic_url = f"https://lunarcrush.com/api4/public/topic/{symbol}/v1"
            
            # Make both requests concurrently
            try:
                coin_response = await client.get(coin_url, headers=headers)
                
                # Handle rate limit
                if coin_response.status_code == 429:
                    logger.warning(f"Rate limit hit for {symbol}, waiting 2 seconds...")
                    await asyncio.sleep(2)
                    return None
                
                topic_response = await client.get(topic_url, headers=headers)
                
                # Handle rate limit
                if topic_response.status_code == 429:
                    logger.warning(f"Rate limit hit for {symbol} topic, waiting 2 seconds...")
                    await asyncio.sleep(2)
                    return None
                    
            except httpx.TimeoutException:
                logger.warning(f"LunarCrush API timeout for {symbol}")
                return None
            except Exception as e:
                logger.error(f"LunarCrush API error: {e}")
                return None
            
            result = {}
            
            # Process coin data
            if coin_response.status_code == 200:
                coin_data = coin_response.json()
                if 'data' in coin_data:
                    result['coin'] = coin_data['data']
            
            # Process topic data
            if topic_response.status_code == 200:
                topic_data = topic_response.json()
                if 'data' in topic_data:
                    result['topic'] = topic_data['data']
            
            if not result:
                logger.warning(f"No data found for symbol {symbol}")
                return None
            
            # Cache the result
            _marketcap_cache[cache_key] = (result, time.time())
            
            return result
        
    except Exception as e:
        logger.error(f"Error fetching LunarCrush data: {e}")
        return None


def calculate_sentiment_from_lunarcrush(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate sentiment metrics from LunarCrush data
    """
    if not data:
        return None
    
    coin_data = data.get('coin', {})
    topic_data = data.get('topic', {})
    
    # Extract basic coin metrics
    galaxy_score = coin_data.get('galaxy_score', 0)  # 0-100 overall score
    alt_rank = coin_data.get('alt_rank', 0)  # Lower is better
    
    # Extract social metrics from topic data
    interactions_24h = topic_data.get('interactions_24h', 0)
    num_posts = topic_data.get('num_posts', 0)
    topic_rank = topic_data.get('topic_rank', 0)
    trend = topic_data.get('trend', 'neutral')
    
    # Get sentiment by type
    types_sentiment = topic_data.get('types_sentiment', {})
    tweet_sentiment = types_sentiment.get('tweet', 50)  # 0-100 scale
    news_sentiment = types_sentiment.get('news', 50)
    reddit_sentiment = types_sentiment.get('reddit-post', 50)
    
    # Get post counts by type
    types_count = topic_data.get('types_count', {})
    tweets_total = types_count.get('tweet', 0)
    news_count = types_count.get('news', 0)
    reddit_count = types_count.get('reddit-post', 0)
    
    # Calculate weighted average sentiment
    total_sentiment = (tweet_sentiment + news_sentiment + reddit_sentiment) / 3
    
    # Use galaxy score as primary sentiment score (0-100)
    sentiment_score = galaxy_score if galaxy_score > 0 else total_sentiment
    
    # Determine sentiment category
    if sentiment_score >= 70:
        sentiment_label = 'very_bullish'
    elif sentiment_score >= 60:
        sentiment_label = 'bullish'
    elif sentiment_score >= 40:
        sentiment_label = 'neutral'
    elif sentiment_score >= 30:
        sentiment_label = 'bearish'
    else:
        sentiment_label = 'very_bearish'
    
    # Simpler twitter sentiment
    if tweet_sentiment >= 60:
        twitter_sentiment = 'bullish'
    elif tweet_sentiment <= 40:
        twitter_sentiment = 'bearish'
    else:
        twitter_sentiment = 'neutral'
    
    return {
        'sentiment_score': round(sentiment_score, 2),
        'twitter_sentiment': twitter_sentiment,
        'sentiment_label': sentiment_label,
        'galaxy_score': galaxy_score,
        'alt_rank': alt_rank,
        'topic_rank': topic_rank,
        'social_volume': num_posts,
        'interactions_24h': interactions_24h,
        'tweets_24h': tweets_total,
        'news_24h': news_count,
        'reddit_24h': reddit_count,
        'tweet_sentiment': tweet_sentiment,
        'news_sentiment': news_sentiment,
        'reddit_sentiment': reddit_sentiment,
        'trend': trend,
        'data_source': 'LunarCrush'
    }


@router.get("/api/social-sentiment/{symbol}")
async def get_social_sentiment(symbol: str):
    """
    Get social sentiment data for a cryptocurrency symbol using LunarCrush
    """
    try:
        # Remove common suffixes and get base symbol
        base_symbol = get_lunarcrush_symbol(symbol)
        logger.info(f"Fetching social sentiment for {symbol} (LunarCrush: {base_symbol})")
        
        # Fetch data from LunarCrush (await the async function)
        data = await fetch_lunarcrush_data(base_symbol)
        
        if not data:
            raise HTTPException(status_code=404, detail="Social data not available for this symbol")
        
        # Calculate sentiment metrics
        result = calculate_sentiment_from_lunarcrush(data)
        
        if not result:
            raise HTTPException(status_code=404, detail="Unable to process social data for this symbol")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_social_sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/social-traction")
async def get_social_traction_predictions(debug: bool = False):
    """
    Advanced prediction: Find the next 10x - newly listed or upcoming coins
    
    Discovers low-cap coins recently listed on Binance that are gaining social
    traction before major price moves. Perfect for finding gems early.
    
    Strategy:
    1. Fetch all USDT pairs from Binance
    2. Filter for low market cap coins (< $500M)
    3. Cross-reference with LunarCrush for social metrics
    4. Identify coins with high social buzz but haven't mooned yet
    
    Returns coins with potential for 10x+ gains
    """
    logger.info("=" * 80)
    logger.info("STARTING SOCIAL TRACTION ANALYSIS")
    logger.info("=" * 80)
    
    try:
        results = []
        diagnostics = {
            'total_symbols': 0,
            'usdt_pairs': 0,
            'volume_filtered': 0,
            'top_by_volume_checked': 0,
            'marketcap_hits': 0,
            'samples': {
                'usdt_pairs_sample': [],
                'volume_filtered_sample': [],
                'marketcap_checked_sample': []
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get all trading pairs from Binance to find new listings
            try:
                logger.info("Step 1: Fetching Binance exchange info...")
                binance_url = "https://api.binance.com/api/v3/exchangeInfo"
                binance_response = await client.get(binance_url)
                
                logger.info(f"Binance response status: {binance_response.status_code}")
                
                if binance_response.status_code != 200:
                    logger.error(f"Binance API error: {binance_response.status_code}")
                    return {
                        'success': False,
                        'error': 'Failed to fetch Binance exchange info',
                        'predictions': []
                    }
                
                binance_data = binance_response.json()
                symbols_list = binance_data.get('symbols', [])
                diagnostics['total_symbols'] = len(symbols_list)
                logger.info(f"Got {len(symbols_list)} total symbols from Binance")
                
                # Extract USDT trading pairs only (spot market)
                usdt_pairs = []
                for symbol_info in symbols_list:
                    if symbol_info.get('status') != 'TRADING':
                        continue
                    
                    symbol = symbol_info.get('symbol', '')
                    base = symbol_info.get('baseAsset', '')
                    quote = symbol_info.get('quoteAsset', '')
                    
                    # Only USDT pairs, exclude stablecoins, wrapped tokens, and OLD established coins
                    # We want NEW listings only - coins with real 10x potential
                    old_coins = [
                        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'WBTC', 'WETH', 'BTC', 'ETH', 'BNB',
                        # Exclude established top 100 projects (these are NOT emerging gems)
                        'XRP', 'ADA', 'SOL', 'DOGE', 'MATIC', 'DOT', 'AVAX', 'SHIB', 'LTC', 'TRX',
                        'LINK', 'ATOM', 'UNI', 'XMR', 'ETC', 'BCH', 'XLM', 'ALGO', 'VET', 'ICP',
                        'FIL', 'HBAR', 'APE', 'NEAR', 'AAVE', 'SAND', 'MANA', 'AXS', 'THETA',
                        'FTM', 'EOS', 'EGLD', 'XTZ', 'RUNE', 'KCS', 'CAKE', 'CRV', 'KLAY',
                        'GRT', 'ENJ', 'ZEC', 'FLOW', 'NEO', 'CHZ', 'WAVES', 'DASH', 'BAT',
                        'COMP', 'YFI', 'ZIL', 'HOT', 'QTUM', 'OMG', 'SUSHI', 'CELO', 'ONT',
                        '1INCH', 'SNX', 'IOTX', 'RVN', 'IOST', 'ZRX', 'ICX', 'BTG', 'SC',
                        'LSK', 'DGB', 'STEEM', 'STMX', 'BNT', 'STORJ', 'MATIC', 'SKL', 'ANKR',
                        'LRC', 'OCEAN', 'REEF', 'SXP', 'CELR', 'COTI', 'CHR', 'DENT', 'WIN',
                        'FET', 'CTSI', 'BAND', 'DUSK', 'PERP', 'NKN', 'WRX', 'KAVA', 'ARPA',
                        'CTXC', 'HARD', 'BAKE', 'FOR', 'BEL', 'WING', 'LIT', 'POLS', 'UNFI',
                        'OXT', 'SUN', 'AVA', 'BAL', 'FIO', 'WNXM', 'MBL', 'BURGER', 'SLP',
                        'TRU', 'BADGER', 'RAMP', 'PUNDIX', 'TKO', 'ALICE', 'LINA', 'PHA',
                        'DODO', 'MASK', 'LPT', 'NU', 'RLC', 'INJ', 'AUDIO', 'C98', 'JASMY',
                        'AMP', 'PLA', 'REN', 'GTC', 'TRIBE', 'ERN', 'QUICK', 'SUPER', 'CFX',
                        'EPX', 'VOXEL', 'HIGH', 'CVX', 'PEOPLE', 'SPELL', 'BICO', 'FLUX',
                        'VELO', 'ACA', 'ANC', 'XNO', 'WOO', 'ALPINE', 'APT', 'BSW', 'GMT',
                        'KDA', 'FXS', 'NEXO', 'SYN', 'LUNC', 'LUNA', 'USTC', 'OP', 'ROSE',
                        'GLMR', 'ASTR', 'MOVR', 'GALA', 'LDO', 'BSV', 'AGIX', 'GMX', 'MAV',
                        'EDU', 'ARB', 'SUI', 'PEPE', 'FLOKI', 'PENDLE', 'SEI', 'CYBER',
                        'BLUR', 'WLD', 'TIA', 'ORDI', 'BONK', 'PYTH', 'MANTA', 'ONDO',
                        'STRK', 'PORTAL', 'PIXEL', 'AEVO', 'JUP', 'DYM', 'METIS', 'WIF'
                    ]
                    
                    if quote == 'USDT' and base not in old_coins:
                        usdt_pairs.append({
                            'symbol': symbol,
                            'base': base
                        })
                
                diagnostics['usdt_pairs'] = len(usdt_pairs)
                # capture small sample
                diagnostics['samples']['usdt_pairs_sample'] = usdt_pairs[:8]
                logger.info(f"Found {len(usdt_pairs)} USDT trading pairs on Binance")
                
                # Step 2: Get 24h ticker data and current prices
                ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
                ticker_response = await client.get(ticker_url)
                
                if ticker_response.status_code != 200:
                    logger.error(f"Binance ticker API error: {ticker_response.status_code}")
                    # Continue without ticker data
                    ticker_data_map = {}
                else:
                    ticker_data = ticker_response.json()
                    ticker_data_map = {item['symbol']: item for item in ticker_data}
                
                # Step 3: Get market cap data from CoinGecko or similar
                # We'll use a simple approximation: fetch circulating supply * price
                # For more accurate data, we can query CoinGecko API
                    # Step 3: Get market cap data from CoinGecko or similar
                # We'll use a simple approximation: fetch circulating supply * price
                # For more accurate data, we can query CoinGecko API
            
            except Exception as e:
                logger.error(f"Error fetching Binance data: {e}")
                return {
                    'success': False,
                    'error': f'Binance API error: {str(e)}',
                    'predictions': []
                }
            
            # Step 4: Filter candidates by volume first, then check market cap
            # More efficient: filter by volume first to reduce API calls
            filtered_pairs = []
            
            logger.info(f"Pre-filtering {len(usdt_pairs)} pairs by volume...")
            
            # Pre-filter by volume to reduce API calls
            volume_filtered = []
            for pair in usdt_pairs:
                ticker = ticker_data_map.get(pair['symbol'])
                if not ticker:
                    continue
                
                try:
                    volume_usdt = float(ticker.get('quoteVolume', 0))
                    price_change_24h = float(ticker.get('priceChangePercent', 0))
                    
                    # Pre-filter: reasonable volume range, not massively pumped
                    # Using volume as initial filter (usually correlates with market cap)
                    if 50_000 <= volume_usdt <= 50_000_000 and price_change_24h < 100:
                        volume_filtered.append({
                            'symbol': pair['symbol'],
                            'base': pair['base'],
                            'volume_24h': volume_usdt,
                            'price_change_24h': price_change_24h
                        })
                except (ValueError, TypeError):
                    continue
            
            diagnostics['volume_filtered'] = len(volume_filtered)
            diagnostics['samples']['volume_filtered_sample'] = volume_filtered[:8]
            logger.info(f"Volume pre-filter found {len(volume_filtered)} pairs out of {len(usdt_pairs)} total")
            
            # Sort by volume and take top candidates
            volume_filtered.sort(key=lambda x: x['volume_24h'], reverse=True)
            top_by_volume = volume_filtered[:150]  # Check top 150 by volume
            
            logger.info(f"Checking market cap for {len(top_by_volume)} volume-filtered pairs...")
            
            headers = {
                "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Now check market cap for these pre-filtered candidates
            checked_count = 0
            for pair in top_by_volume:
                try:
                    base_symbol = pair['base']
                    checked_count += 1
                    
                    # Get market cap from LunarCrush
                    coin_url = f"https://lunarcrush.com/api4/public/coins/{base_symbol}/v1"
                    
                    try:
                        coin_response = await client.get(coin_url, headers=headers, timeout=5.0)
                        
                        if coin_response.status_code != 200:
                            logger.debug(f"{base_symbol}: API returned {coin_response.status_code}")
                            continue
                        
                        coin_data = coin_response.json().get('data', {})
                        market_cap = coin_data.get('market_cap', 0)
                        
                        if market_cap == 0:
                            logger.debug(f"{base_symbol}: No market cap data")
                            diagnostics['samples']['marketcap_checked_sample'].append({'base': base_symbol, 'status': 'no_marketcap'})
                            continue

                        logger.info(f"{base_symbol}: Market Cap ${market_cap/1e6:.1f}M, Volume ${pair['volume_24h']/1e6:.1f}M")
                        diagnostics['samples']['marketcap_checked_sample'].append({'base': base_symbol, 'market_cap': market_cap})
                        
                        # Filter: market cap between $1M and $500M (relaxed for more gems)
                        if 1_000_000 <= market_cap <= 500_000_000:
                            filtered_pairs.append({
                                'symbol': pair['symbol'],
                                'base': base_symbol,
                                'market_cap': market_cap,
                                'volume_24h': pair['volume_24h'],
                                'price_change_24h': pair['price_change_24h']
                            })
                            diagnostics['marketcap_hits'] = diagnostics.get('marketcap_hits', 0) + 1
                            logger.info(f"✓ Added {base_symbol}: Market Cap ${market_cap/1e6:.1f}M")
                    
                    except httpx.TimeoutException:
                        logger.debug(f"Timeout for {base_symbol}")
                        continue
                    except Exception as e:
                        logger.debug(f"Error for {base_symbol}: {e}")
                        continue
                        
                except Exception:
                    continue
                
                # Stop early if we have enough candidates
                if len(filtered_pairs) >= 100:
                    break
            
            diagnostics['top_by_volume_checked'] = checked_count
            logger.info(f"Checked {checked_count} coins, found {len(filtered_pairs)} within $1M-$500M market cap range")
            
            # Sort by market cap (smaller = more potential)
            filtered_pairs.sort(key=lambda x: x['market_cap'])
            
            # Take top 100 candidates
            candidates = filtered_pairs[:100]
            
            logger.info(f"Found {len(candidates)} candidates with market cap between $20M-$200M")
            
            # Step 5: Analyze social data for filtered candidates
            for candidate in candidates:
                try:
                    base_symbol = candidate['base']
                    
                    # Fetch LunarCrush topic data (we already have coin data from filtering)
                    topic_url = f"https://lunarcrush.com/api4/public/topic/{base_symbol}/v1"
                    
                    coin_url = f"https://lunarcrush.com/api4/public/coins/{base_symbol}/v1"
                    coin_response = await client.get(coin_url, headers=headers, timeout=3.0)
                    topic_response = await client.get(topic_url, headers=headers, timeout=3.0)
                    
                    # Skip if no social data available
                    if coin_response.status_code != 200 or topic_response.status_code != 200:
                        continue
                    
                    coin_data = coin_response.json().get('data', {})
                    topic_data = topic_response.json().get('data', {})
                    
                    if not coin_data or not topic_data:
                        continue
                    
                    # Extract social metrics
                    galaxy_score = coin_data.get('galaxy_score', 0)
                    alt_rank = coin_data.get('alt_rank', 9999)
                    interactions_24h = topic_data.get('interactions_24h', 0)
                    num_posts = topic_data.get('num_posts', 0)
                    
                    # Get sentiment
                    types_sentiment = topic_data.get('types_sentiment', {})
                    tweet_sentiment = types_sentiment.get('tweet', 50) / 100
                    
                    # Get price changes from LunarCrush (more reliable)
                    price_change_24h = coin_data.get('percent_change_24h', candidate['price_change_24h'])
                    price_change_7d = coin_data.get('percent_change_7d', 0)
                    
                    # Calculate "GEM SCORE" - optimized for finding 10x potential
                    gem_score = 0
                    
                    # CRITICAL: Must have social activity (no social = skip)
                    # Relaxed to 10 interactions to catch early gems
                    if interactions_24h < 10:
                        continue
                    
                    # Bonus for newer coins (higher alt_rank = less established = more 10x potential)
                    # Alt rank > 500 means it's not a top coin yet
                    if alt_rank > 1000:
                        gem_score += 40  # Very new/unknown = highest potential
                    elif alt_rank > 500:
                        gem_score += 30  # Mid-tier = good potential
                    elif alt_rank > 200:
                        gem_score += 15  # Getting established
                    
                    # Bonus for growing social presence (galaxy score 30-70 = emerging)
                    if 30 <= galaxy_score <= 70:
                        gem_score += 35  # Sweet spot - not too big, not too small
                    elif galaxy_score > 70:
                        gem_score += 20  # Already popular
                    elif galaxy_score > 15:
                        gem_score += 10  # Very early
                    
                    # Bonus for social engagement (early buzz)
                    if 1000 <= interactions_24h < 10000:
                        gem_score += 30  # Early traction, not mainstream yet
                    elif interactions_24h >= 10000:
                        gem_score += 20  # Good buzz
                    elif interactions_24h >= 500:
                        gem_score += 15  # Some interest
                    
                    # Bonus for positive sentiment
                    if tweet_sentiment > 0.65:
                        gem_score += 25  # Very bullish community
                    elif tweet_sentiment > 0.55:
                        gem_score += 15
                    
                    # Bonus for volume (shows liquidity)
                    if candidate['volume_24h'] > 5_000_000:
                        gem_score += 20
                    elif candidate['volume_24h'] > 1_000_000:
                        gem_score += 10
                    
                    # Price action analysis
                    abs_change_24h = abs(price_change_24h)
                    abs_change_7d = abs(price_change_7d)
                    
                    # Bonus for consolidation (building base before breakout)
                    if abs_change_24h < 5 and abs_change_7d < 15:
                        gem_score += 20  # Consolidating = potential energy
                    
                    # Penalty for recent dump
                    if price_change_24h < -15:
                        gem_score -= 30
                    elif price_change_24h < -10:
                        gem_score -= 15
                    
                    # Penalty for already pumped
                    if price_change_24h > 30:
                        gem_score -= 20  # Already moved
                    
                    # Relaxed threshold to catch more early gems
                    if gem_score < 20:
                        continue
                    
                    results.append({
                        'symbol': candidate['symbol'],
                        'base': base_symbol,
                        'market_cap': candidate['market_cap'],
                        'traction_score': gem_score,
                        'galaxy_score': galaxy_score,
                        'alt_rank': alt_rank,
                        'interactions_24h': interactions_24h,
                        'num_posts': num_posts,
                        'tweet_sentiment': tweet_sentiment,
                        'price_change_24h': price_change_24h,
                        'price_change_7d': price_change_7d,
                        'volume_24h': candidate['volume_24h'],
                        'prediction': 'HIGH' if gem_score > 80 else 'MEDIUM' if gem_score > 60 else 'LOW',
                        'reason': generate_gem_reason(
                            gem_score, galaxy_score, interactions_24h,
                            tweet_sentiment, price_change_24h, candidate['volume_24h'],
                            candidate['market_cap']
                        )
                    })
                    
                    # Limit to prevent timeout
                    if len(results) >= 20:
                        break
                    
                except Exception as e:
                    logger.debug(f"Error analyzing {candidate.get('base')}: {e}")
                    continue
        
        # Sort by gem score (highest first)
        results.sort(key=lambda x: x['traction_score'], reverse=True)
        
        # Return top 8 gems
        response = {
            'success': True,
            'predictions': results[:8],
            'total_analyzed': len(candidates),
            'total_predictions': len(results),
            'strategy': 'low_cap_gems'
        }
        if debug:
            response['diagnostics'] = diagnostics
        return response
        
    except Exception as e:
        logger.error(f"Error in social traction predictions: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/volume-surges")
async def get_volume_surges(
    min_surge_multiplier: float = 3.0,
    max_price_change: float = 5.0,
    lookback_hours: int = 168,  # 7 days
    top_n: int = 5  # Show only top 5 most confident
):
    """
    Detect volume surges - early indicator of big moves
    
    Strategy:
    - Compare current volume vs average volume on BOTH 1h and 4h timeframes
    - 1h = Early detection, 4h = Trend confirmation
    - Alert when volume is 3x+ average BUT price hasn't moved much yet
    - This catches accumulation/distribution BEFORE the pump
    
    Multi-timeframe scoring:
    - Both 1h AND 4h surge = VERY STRONG signal
    - Only 1h surge = Early signal (may need confirmation)
    - Only 4h surge = Established trend
    
    Parameters:
    - min_surge_multiplier: Minimum volume multiplier (default 3x)
    - max_price_change: Max price change to filter already pumped coins (default 5%)
    - lookback_hours: Hours to calculate average volume (default 168 = 7 days)
    - top_n: Number of results to return
    """
    logger.info("=" * 80)
    logger.info("MULTI-TIMEFRAME VOLUME SURGE DETECTION (1h + 4h)")
    logger.info(f"Parameters: surge_mult={min_surge_multiplier}x, max_price={max_price_change}%, lookback={lookback_hours}h")
    logger.info("=" * 80)
    
    try:
        results = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get current 24h ticker data from Binance
            logger.info("Fetching 24h ticker data from Binance...")
            ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
            ticker_response = await client.get(ticker_url)
            
            if ticker_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch Binance ticker data")
            
            ticker_data = ticker_response.json()
            logger.info(f"Got {len(ticker_data)} tickers from Binance")
            
            # Filter for USDT pairs with reasonable volume
            usdt_tickers = []
            for ticker in ticker_data:
                symbol = ticker.get('symbol', '')
                if not symbol.endswith('USDT'):
                    continue
                
                # Skip stablecoins, leveraged tokens, old versions
                base = symbol.replace('USDT', '')
                skip_tokens = ['USDC', 'BUSD', 'DAI', 'TUSD', 'UP', 'DOWN', 'BULL', 'BEAR']
                if any(skip in base for skip in skip_tokens):
                    continue
                if base.endswith('3L') or base.endswith('3S'):
                    continue
                
                try:
                    quote_volume_24h = float(ticker.get('quoteVolume', 0))
                    price_change_pct = float(ticker.get('priceChangePercent', 0))
                    
                    # Pre-filter: must have some volume
                    if quote_volume_24h > 10_000:
                        usdt_tickers.append({
                            'symbol': symbol,
                            'base': base,
                            'quote_volume_24h': quote_volume_24h,
                            'price_change_24h': price_change_pct,
                            'last_price': float(ticker.get('lastPrice', 0))
                        })
                except (ValueError, TypeError):
                    continue
            
            logger.info(f"Filtered to {len(usdt_tickers)} USDT pairs with >$10k volume")
            
            # Pre-sort by volume and only analyze top 50 (speed optimization)
            usdt_tickers.sort(key=lambda x: x['quote_volume_24h'], reverse=True)
            usdt_tickers = usdt_tickers[:50]
            logger.info(f"Analyzing top {len(usdt_tickers)} by volume for speed")
            
            # Step 2: For each ticker, fetch historical klines to calculate average volume
            logger.info(f"Analyzing volume patterns for top candidates (1h + 4h timeframes)...")
            
            # Sort by 24h volume and analyze top candidates
            usdt_tickers.sort(key=lambda x: x['quote_volume_24h'], reverse=True)
            top_candidates = usdt_tickers[:200]  # Analyze top 200 by volume
            
            top_5_vol = [(t['symbol'], f"${t['quote_volume_24h']/1e6:.1f}M") for t in top_candidates[:5]]
            logger.info(f"Top 5 candidates by volume: {top_5_vol}")
            
            checked_count = 0
            failed_fetch = 0
            failed_data = 0
            
            for ticker in top_candidates:
                try:
                    symbol = ticker['symbol']
                    checked_count += 1
                    
                    if checked_count == 1:
                        logger.info(f"Starting analysis loop, first symbol: {symbol}")
                    
                    # Fetch BOTH 1h and 4h klines
                    klines_1h_url = f"https://api.binance.com/api/v3/klines"
                    klines_4h_url = f"https://api.binance.com/api/v3/klines"
                    
                    # For 1h: Get 168 candles (7 days)
                    params_1h = {
                        'symbol': symbol,
                        'interval': '1h',
                        'limit': min(lookback_hours, 1000)
                    }
                    
                    # For 4h: Get 42 candles (7 days = 168h / 4h = 42 candles)
                    params_4h = {
                        'symbol': symbol,
                        'interval': '4h',
                        'limit': min(lookback_hours // 4, 250)
                    }
                    
                    # Fetch both in parallel
                    klines_1h_response, klines_4h_response = await asyncio.gather(
                        client.get(klines_1h_url, params=params_1h),
                        client.get(klines_4h_url, params=params_4h),
                        return_exceptions=True
                    )
                    
                    # Check if both requests succeeded
                    if isinstance(klines_1h_response, Exception) or isinstance(klines_4h_response, Exception):
                        failed_fetch += 1
                        if failed_fetch <= 3:
                            logger.warning(f"{symbol}: API request failed (exception)")
                        continue
                    
                    if klines_1h_response.status_code != 200 or klines_4h_response.status_code != 200:
                        failed_fetch += 1
                        if failed_fetch <= 3:
                            logger.warning(f"{symbol}: API returned status {klines_1h_response.status_code}/{klines_4h_response.status_code}")
                        continue
                    
                    klines_1h = klines_1h_response.json()
                    klines_4h = klines_4h_response.json()
                    
                    if len(klines_1h) < 24 or len(klines_4h) < 6:  # Need minimum data
                        failed_data += 1
                        if failed_data <= 3:
                            logger.warning(f"{symbol}: Insufficient data - 1h:{len(klines_1h)} candles, 4h:{len(klines_4h)} candles")
                        continue
                    
                    # ==================== 1H ANALYSIS ====================
                    # Calculate average hourly volume over lookback period
                    # Kline format: [timestamp, open, high, low, close, volume, close_time, quote_volume, ...]
                    historical_volumes_1h = []
                    for kline in klines_1h[:-1]:  # Exclude last candle (current incomplete hour)
                        try:
                            quote_volume = float(kline[7])  # Quote asset volume
                            historical_volumes_1h.append(quote_volume)
                        except (ValueError, IndexError):
                            continue
                    
                    if len(historical_volumes_1h) < 24:
                        continue
                    
                    avg_hourly_volume_1h = sum(historical_volumes_1h) / len(historical_volumes_1h)
                    
                    # Get current 1h volume (last complete candle)
                    try:
                        current_1h_volume = float(klines_1h[-2][7])  # Second to last (complete candle)
                    except (ValueError, IndexError):
                        continue
                    
                    # Calculate 1h surge multiplier
                    surge_multiplier_1h = current_1h_volume / avg_hourly_volume_1h if avg_hourly_volume_1h > 0 else 0
                    
                    # Get recent price change (last 1h)
                    try:
                        price_open_1h = float(klines_1h[-2][1])
                        price_close_1h = float(klines_1h[-2][4])
                        price_change_1h = ((price_close_1h - price_open_1h) / price_open_1h) * 100
                    except (ValueError, IndexError, ZeroDivisionError):
                        price_change_1h = 0
                    
                    # ==================== 4H ANALYSIS ====================
                    historical_volumes_4h = []
                    for kline in klines_4h[:-1]:  # Exclude last candle
                        try:
                            quote_volume = float(kline[7])
                            historical_volumes_4h.append(quote_volume)
                        except (ValueError, IndexError):
                            continue
                    
                    if len(historical_volumes_4h) < 6:
                        continue
                    
                    # Average volume per 4h candle
                    avg_volume_4h = sum(historical_volumes_4h) / len(historical_volumes_4h)
                    
                    # Get current 4h volume
                    try:
                        current_4h_volume = float(klines_4h[-2][7])
                    except (ValueError, IndexError):
                        continue
                    
                    # Calculate 4h surge multiplier
                    surge_multiplier_4h = current_4h_volume / avg_volume_4h if avg_volume_4h > 0 else 0
                    
                    # Get 4h price change
                    try:
                        price_open_4h = float(klines_4h[-2][1])
                        price_close_4h = float(klines_4h[-2][4])
                        price_change_4h = ((price_close_4h - price_open_4h) / price_open_4h) * 100
                    except (ValueError, IndexError, ZeroDivisionError):
                        price_change_4h = 0
                    
                    # ==================== MULTI-TIMEFRAME FILTERING ====================
                    # Flag if EITHER timeframe shows surge (but prioritize when both agree)
                    surge_1h = surge_multiplier_1h >= min_surge_multiplier
                    surge_4h = surge_multiplier_4h >= min_surge_multiplier
                    
                    # Price stability check (use 1h for more sensitivity)
                    price_stable = abs(price_change_1h) <= max_price_change
                    
                    # Log first 10 for debugging
                    if checked_count <= 10:
                        logger.info(f"Sample {checked_count} - {symbol}: 1h={surge_multiplier_1h:.2f}x (need {min_surge_multiplier}), 4h={surge_multiplier_4h:.2f}x, price_1h={price_change_1h:+.2f}% (max {max_price_change})")
                    
                    if (surge_1h or surge_4h) and price_stable:
                        
                        # Calculate volume trend (is it accelerating?) - using 1h data
                        recent_volumes = historical_volumes_1h[-24:]  # Last 24 hours
                        older_volumes = historical_volumes_1h[:24] if len(historical_volumes_1h) >= 48 else historical_volumes_1h[:len(historical_volumes_1h)//2]
                        
                        recent_avg = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
                        older_avg = sum(older_volumes) / len(older_volumes) if older_volumes else 0
                        
                        volume_trend = "accelerating" if recent_avg > older_avg * 1.5 else "stable" if recent_avg > older_avg else "declining"
                        
                        # ==================== TIMEFRAME ALIGNMENT ====================
                        timeframe_alignment = "none"
                        if surge_1h and surge_4h:
                            timeframe_alignment = "both"  # STRONGEST signal
                        elif surge_1h:
                            timeframe_alignment = "1h_only"  # Early signal
                        elif surge_4h:
                            timeframe_alignment = "4h_only"  # Trend confirmation
                        
                        # ==================== CONFIDENCE SCORING ====================
                        # Base confidence from surge magnitude (using the higher of the two)
                        max_surge = max(surge_multiplier_1h, surge_multiplier_4h)
                        confidence = min(100, (max_surge / min_surge_multiplier) * 40)
                        
                        # MAJOR BONUS for both timeframes aligning
                        if timeframe_alignment == "both":
                            confidence += 30  # Both TF = very strong
                        elif timeframe_alignment == "1h_only":
                            confidence += 10  # Early signal
                        elif timeframe_alignment == "4h_only":
                            confidence += 15  # Trend established
                        
                        # Bonus for accelerating volume
                        if volume_trend == "accelerating":
                            confidence += 15
                        
                        # Penalty for already moved price
                        confidence -= abs(price_change_1h) * 2
                        
                        confidence = max(0, min(100, confidence))
                        
                        # ==================== SIGNAL STRENGTH ====================
                        # Determine signal strength based on multi-timeframe analysis
                        if timeframe_alignment == "both" and confidence > 75:
                            signal = "VERY_STRONG"
                        elif max_surge >= 5 and confidence > 70:
                            signal = "STRONG"
                        elif max_surge >= 4 or confidence > 50:
                            signal = "MEDIUM"
                        else:
                            signal = "WEAK"
                        
                        results.append({
                            'symbol': symbol,
                            'base': ticker['base'],
                            'surge_multiplier_1h': round(surge_multiplier_1h, 2),
                            'surge_multiplier_4h': round(surge_multiplier_4h, 2),
                            'surge_multiplier': round(max_surge, 2),  # For backward compatibility
                            'current_1h_volume': round(current_1h_volume, 2),
                            'current_4h_volume': round(current_4h_volume, 2),
                            'avg_hourly_volume': round(avg_hourly_volume_1h, 2),
                            'avg_4h_volume': round(avg_volume_4h, 2),
                            'volume_24h': ticker['quote_volume_24h'],
                            'price_change_1h': round(price_change_1h, 2),
                            'price_change_4h': round(price_change_4h, 2),
                            'price_change_24h': ticker['price_change_24h'],
                            'last_price': ticker['last_price'],
                            'volume_trend': volume_trend,
                            'timeframe_alignment': timeframe_alignment,
                            'confidence': round(confidence, 1),
                            'signal': signal,
                            'reason': generate_volume_surge_reason(
                                max_surge, price_change_1h, volume_trend, confidence, 
                                timeframe_alignment, surge_multiplier_1h, surge_multiplier_4h
                            )
                        })
                        
                        logger.info(f"✓ {symbol}: 1h={surge_multiplier_1h:.1f}x, 4h={surge_multiplier_4h:.1f}x, align={timeframe_alignment}, conf={confidence:.0f}%, signal={signal}")
                
                except Exception as e:
                    logger.debug(f"Error analyzing {ticker.get('symbol')}: {e}")
                    if checked_count <= 3:
                        logger.error(f"Exception on symbol {checked_count} ({ticker.get('symbol')}): {e}")
                    continue
                
                # Limit results
                if len(results) >= 50:
                    break
            
            # Sort by confidence score
            results.sort(key=lambda x: x['confidence'], reverse=True)
            
            logger.info(f"Analysis complete: Checked {checked_count} pairs, API failures: {failed_fetch}, insufficient data: {failed_data}, found {len(results)} surges")
            if len(results) == 0:
                logger.warning(f"No surges found! Try lowering min_surge_multiplier (current: {min_surge_multiplier}) or increasing max_price_change (current: {max_price_change})")
            
            return {
                'success': True,
                'surges': results[:top_n],
                'total_analyzed': len(top_candidates),
                'total_surges': len(results),
                'parameters': {
                    'min_surge_multiplier': min_surge_multiplier,
                    'max_price_change': max_price_change,
                    'lookback_hours': lookback_hours,
                    'timeframes': ['1h', '4h']
                }
            }
    
    except Exception as e:
        logger.error(f"Error in volume surge detection: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


def generate_volume_surge_reason(surge_mult, price_change, volume_trend, confidence, 
                                  timeframe_alignment, surge_1h, surge_4h):
    """Generate human-readable explanation for volume surge with multi-timeframe context"""
    reasons = []
    
    # Timeframe alignment (most important signal)
    if timeframe_alignment == "both":
        reasons.append(f"🔥 BOTH 1h ({surge_1h:.1f}x) & 4h ({surge_4h:.1f}x) surging")
    elif timeframe_alignment == "1h_only":
        reasons.append(f"⚡ Early 1h surge ({surge_1h:.1f}x)")
    elif timeframe_alignment == "4h_only":
        reasons.append(f"📊 4h trend confirmed ({surge_4h:.1f}x)")
    
    # Price action
    if abs(price_change) < 1:
        reasons.append("price stable (early accumulation)")
    elif abs(price_change) < 3:
        reasons.append(f"price {price_change:+.1f}% (early move)")
    else:
        reasons.append(f"price {price_change:+.1f}%")
    
    # Volume trend
    if volume_trend == "accelerating":
        reasons.append("volume accelerating")
    elif volume_trend == "declining":
        reasons.append("volume declining")
    
    # Confidence assessment
    if confidence > 85:
        reasons.append("VERY HIGH CONFIDENCE")
    elif confidence > 70:
        reasons.append("HIGH CONFIDENCE")
    elif confidence > 50:
        reasons.append("good confidence")
    
    return " • ".join(reasons)


def generate_gem_reason(gem_score, galaxy_score, interactions, sentiment, change_24h, volume_24h, market_cap):
    """Generate human-readable reason for gem prediction"""
    reasons = []
    
    # Market cap
    if market_cap < 50_000_000:
        reasons.append(f"Micro-cap (${market_cap/1e6:.1f}M)")
    elif market_cap < 100_000_000:
        reasons.append(f"Small-cap (${market_cap/1e6:.1f}M)")
    else:
        reasons.append(f"Mid-cap (${market_cap/1e6:.1f}M)")
    
    # Social metrics
    if 30 <= galaxy_score <= 70:
        reasons.append(f"Emerging project (Galaxy: {galaxy_score}/100)")
    elif galaxy_score > 70:
        reasons.append(f"Popular project (Galaxy: {galaxy_score}/100)")
    
    if 1000 <= interactions < 10000:
        reasons.append(f"Early social traction ({interactions:,} interactions)")
    elif interactions >= 10000:
        reasons.append(f"Strong buzz ({interactions:,} interactions)")
    elif interactions >= 500:
        reasons.append(f"Growing community ({interactions:,} interactions)")
    
    # Sentiment
    if sentiment > 0.65:
        reasons.append(f"Very bullish sentiment ({sentiment:.0%})")
    elif sentiment > 0.55:
        reasons.append(f"Positive sentiment ({sentiment:.0%})")
    
    # Volume = liquidity
    if volume_24h > 5_000_000:
        reasons.append(f"Good liquidity (${volume_24h/1e6:.1f}M vol)")
    elif volume_24h > 1_000_000:
        reasons.append(f"Decent liquidity (${volume_24h/1e6:.1f}M vol)")
    
    # Price action
    if abs(change_24h) < 5:
        reasons.append("Consolidating (potential breakout)")
    elif change_24h > 10:
        reasons.append(f"Momentum building (+{change_24h:.1f}%)")
    
    if not reasons:
        reasons.append("Low-cap opportunity")
    
    return " | ".join(reasons)


@router.get("/api/breakout-scanner")
async def get_breakout_opportunities(
    consolidation_hours: int = 72,  # 3 days default
    min_breakout_pct: float = 2.0,
    min_volume_increase: float = 1.5,
    top_n: int = 5,
    max_market_cap: float = 500_000_000,  # $500M default (mid-low cap filter)
    direction: str = "both"  # "bullish", "bearish", or "both"
):
    """
    Detect breakout opportunities from consolidation patterns
    
    Strategy:
    - Identify coins in tight consolidation (Bollinger Band squeeze)
    - Detect when price breaks out of the range
    - Confirm with volume increase
    - Flag early (within first few hours of breakout)
    
    Patterns detected:
    1. Bollinger Band Squeeze (low volatility → expansion)
    2. Support/Resistance Break
    3. Triangle/Wedge Breakouts
    
    Parameters:
    - consolidation_hours: Minimum hours in consolidation (default 72 = 3 days)
    - min_breakout_pct: Minimum % move to confirm breakout (default 2%)
    - min_volume_increase: Volume multiplier vs average (default 1.5x)
    - top_n: Number of results to return
    - max_market_cap: Maximum market cap in USD (default 500M for mid-low caps)
    - direction: Filter by direction - "bullish" (longs), "bearish" (shorts), or "both" (default)
    """
    logger.info("=" * 80)
    logger.info("BREAKOUT SCANNER")
    logger.info(f"Parameters: consolidation={consolidation_hours}h, breakout={min_breakout_pct}%, vol={min_volume_increase}x, max_mcap=${max_market_cap/1_000_000:.0f}M, direction={direction}")
    logger.info("=" * 80)
    
    try:
        results = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get current 24h ticker data
            logger.info("Fetching 24h ticker data from Binance...")
            ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
            ticker_response = await client.get(ticker_url)
            
            if ticker_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch Binance ticker data")
            
            ticker_data = ticker_response.json()
            
            # Filter for USDT pairs with reasonable volume
            usdt_tickers = []
            for ticker in ticker_data:
                symbol = ticker.get('symbol', '')
                if not symbol.endswith('USDT'):
                    continue
                
                # Skip stablecoins, leveraged tokens
                base = symbol.replace('USDT', '')
                skip_tokens = ['USDC', 'BUSD', 'DAI', 'TUSD', 'UP', 'DOWN', 'BULL', 'BEAR']
                if any(skip in base for skip in skip_tokens):
                    continue
                if base.endswith('3L') or base.endswith('3S'):
                    continue
                
                try:
                    quote_volume_24h = float(ticker.get('quoteVolume', 0))
                    
                    if quote_volume_24h > 100_000:  # Min $100k volume
                        usdt_tickers.append({
                            'symbol': symbol,
                            'base': base,
                            'quote_volume_24h': quote_volume_24h,
                            'price_change_24h': float(ticker.get('priceChangePercent', 0)),
                            'last_price': float(ticker.get('lastPrice', 0))
                        })
                except (ValueError, TypeError):
                    continue
            
            logger.info(f"Filtered to {len(usdt_tickers)} USDT pairs")
            
            # Pre-sort by volume and limit to top 50 (speed optimization)
            usdt_tickers.sort(key=lambda x: x['quote_volume_24h'], reverse=True)
            usdt_tickers = usdt_tickers[:50]
            logger.info(f"Analyzing top {len(usdt_tickers)} by volume for speed")
            
            # Step 1.5: Fetch market cap data from CoinGecko (if filtering enabled)
            market_cap_map = {}
            if max_market_cap and max_market_cap > 0:
                logger.info("Fetching market cap data from CoinGecko...")
                try:
                    # Get all coin IDs
                    coins_list_url = "https://api.coingecko.com/api/v3/coins/list"
                    coins_response = await client.get(coins_list_url)
                    
                    if coins_response.status_code == 200:
                        coins_list = coins_response.json()
                        
                        # Create mapping of symbol to coin ID
                        symbol_to_id = {}
                        for coin in coins_list:
                            symbol = coin.get('symbol', '').upper()
                            coin_id = coin.get('id', '')
                            if symbol and coin_id:
                                if symbol not in symbol_to_id:
                                    symbol_to_id[symbol] = coin_id
                        
                        # Get market data for our tokens
                        bases = [t['base'] for t in usdt_tickers]
                        coin_ids = [symbol_to_id.get(base) for base in bases if symbol_to_id.get(base)]
                        
                        if coin_ids:
                            # Fetch in batches
                            batch_size = 250
                            for i in range(0, len(coin_ids), batch_size):
                                batch = coin_ids[i:i+batch_size]
                                ids_param = ','.join(batch)
                                
                                market_url = "https://api.coingecko.com/api/v3/coins/markets"
                                params = {
                                    'vs_currency': 'usd',
                                    'ids': ids_param,
                                    'per_page': 250
                                }
                                
                                market_response = await client.get(market_url, params=params)
                                
                                if market_response.status_code == 200:
                                    market_data = market_response.json()
                                    for coin in market_data:
                                        symbol = coin.get('symbol', '').upper()
                                        mcap = coin.get('market_cap')
                                        if symbol and mcap:
                                            market_cap_map[symbol] = mcap
                                
                                await asyncio.sleep(0.5)  # Rate limit
                        
                        logger.info(f"Retrieved market caps for {len(market_cap_map)} tokens")
                except Exception as e:
                    logger.warning(f"Failed to fetch market caps: {e}")
            
            # Filter by market cap if enabled
            if max_market_cap and max_market_cap > 0 and market_cap_map:
                original_count = len(usdt_tickers)
                usdt_tickers = [
                    t for t in usdt_tickers
                    if market_cap_map.get(t['base'], 0) <= max_market_cap or t['base'] not in market_cap_map
                ]
                logger.info(f"Market cap filter: {original_count} → {len(usdt_tickers)} pairs")
            
            # Sort by volume and analyze top candidates
            usdt_tickers.sort(key=lambda x: x['quote_volume_24h'], reverse=True)
            top_candidates = usdt_tickers[:200]
            
            # Step 2: Analyze each for breakout patterns
            for ticker in top_candidates:
                try:
                    symbol = ticker['symbol']
                    
                    # Fetch 1h klines to analyze consolidation pattern
                    # Need enough data to detect consolidation period
                    lookback = max(consolidation_hours + 48, 168)  # Extra buffer
                    
                    klines_url = f"https://api.binance.com/api/v3/klines"
                    params = {
                        'symbol': symbol,
                        'interval': '1h',
                        'limit': min(lookback, 1000)
                    }
                    
                    klines_response = await client.get(klines_url, params=params)
                    
                    if klines_response.status_code != 200:
                        continue
                    
                    klines = klines_response.json()
                    
                    if len(klines) < consolidation_hours + 10:
                        continue
                    
                    # ==================== PATTERN ANALYSIS ====================
                    
                    # Extract recent candles for analysis
                    # Format: [timestamp, open, high, low, close, volume, close_time, quote_volume, ...]
                    
                    # Split into: consolidation period + recent breakout period
                    consolidation_candles = klines[-(consolidation_hours + 24):-24]  # The consolidation
                    recent_candles = klines[-24:]  # Last 24h for breakout detection
                    
                    if len(consolidation_candles) < consolidation_hours:
                        continue
                    
                    # Calculate consolidation metrics
                    cons_highs = [float(k[2]) for k in consolidation_candles]
                    cons_lows = [float(k[3]) for k in consolidation_candles]
                    cons_closes = [float(k[4]) for k in consolidation_candles]
                    cons_volumes = [float(k[7]) for k in consolidation_candles]
                    
                    cons_high = max(cons_highs)
                    cons_low = min(cons_lows)
                    cons_range_pct = ((cons_high - cons_low) / cons_low) * 100
                    avg_cons_volume = sum(cons_volumes) / len(cons_volumes)
                    
                    # Bollinger Band squeeze detection: tight range = low volatility
                    # Looking for range < 10% over consolidation period
                    is_consolidating = cons_range_pct < 10
                    
                    if not is_consolidating:
                        continue  # Not in consolidation
                    
                    # Recent price action
                    recent_highs = [float(k[2]) for k in recent_candles]
                    recent_lows = [float(k[3]) for k in recent_candles]
                    recent_closes = [float(k[4]) for k in recent_candles]
                    recent_volumes = [float(k[7]) for k in recent_candles]
                    
                    current_price = recent_closes[-1]
                    recent_high = max(recent_highs)
                    recent_low = min(recent_lows)
                    avg_recent_volume = sum(recent_volumes) / len(recent_volumes)
                    
                    # ==================== BREAKOUT DETECTION ====================
                    
                    # Bullish breakout: price breaks ABOVE consolidation high
                    breakout_above = current_price > cons_high
                    breakout_above_pct = ((current_price - cons_high) / cons_high) * 100 if breakout_above else 0
                    
                    # Bearish breakout: price breaks BELOW consolidation low
                    breakout_below = current_price < cons_low
                    breakout_below_pct = ((cons_low - current_price) / cons_low) * 100 if breakout_below else 0
                    
                    # Volume confirmation
                    volume_increase = avg_recent_volume / avg_cons_volume if avg_cons_volume > 0 else 0
                    
                    # Determine breakout type and strength
                    breakout_direction = None
                    breakout_strength = 0
                    
                    if breakout_above and breakout_above_pct >= min_breakout_pct:
                        breakout_direction = "BULLISH"
                        breakout_strength = breakout_above_pct
                    elif breakout_below and breakout_below_pct >= min_breakout_pct:
                        breakout_direction = "BEARISH"
                        breakout_strength = breakout_below_pct
                    
                    # Apply direction filter
                    direction_filter = direction.lower()
                    if direction_filter != "both":
                        if direction_filter == "bullish" and breakout_direction != "BULLISH":
                            continue
                        elif direction_filter == "bearish" and breakout_direction != "BEARISH":
                            continue
                    
                    # Filter: Must have breakout + volume confirmation
                    if breakout_direction and volume_increase >= min_volume_increase:
                        
                        # Calculate hours since breakout started
                        breakout_start_candle = None
                        for i in range(len(recent_candles) - 1, -1, -1):
                            price = float(recent_candles[i][4])
                            if breakout_direction == "BULLISH" and price <= cons_high:
                                breakout_start_candle = i + 1
                                break
                            elif breakout_direction == "BEARISH" and price >= cons_low:
                                breakout_start_candle = i + 1
                                break
                        
                        hours_since_breakout = len(recent_candles) - breakout_start_candle if breakout_start_candle else 24
                        
                        # Confidence scoring
                        confidence = 0
                        
                        # Tight consolidation = higher confidence
                        if cons_range_pct < 5:
                            confidence += 35
                        elif cons_range_pct < 7:
                            confidence += 25
                        else:
                            confidence += 15
                        
                        # Strong breakout = higher confidence
                        if breakout_strength > 5:
                            confidence += 30
                        elif breakout_strength > 3:
                            confidence += 20
                        else:
                            confidence += 10
                        
                        # Volume confirmation
                        if volume_increase > 3:
                            confidence += 25
                        elif volume_increase > 2:
                            confidence += 15
                        else:
                            confidence += 5
                        
                        # Early detection bonus (fresher = better)
                        if hours_since_breakout <= 2:
                            confidence += 10
                        elif hours_since_breakout <= 6:
                            confidence += 5
                        
                        confidence = min(100, confidence)
                        
                        # Signal strength
                        if confidence > 80:
                            signal = "VERY_STRONG"
                        elif confidence > 65:
                            signal = "STRONG"
                        elif confidence > 50:
                            signal = "MEDIUM"
                        else:
                            signal = "WEAK"
                        
                        # Pattern type
                        if cons_range_pct < 5:
                            pattern_type = "Tight Squeeze"
                        elif cons_range_pct < 7:
                            pattern_type = "Consolidation"
                        else:
                            pattern_type = "Range"
                        
                        results.append({
                            'symbol': symbol,
                            'base': ticker['base'],
                            'breakout_direction': breakout_direction,
                            'breakout_strength': round(breakout_strength, 2),
                            'consolidation_range_pct': round(cons_range_pct, 2),
                            'consolidation_high': cons_high,
                            'consolidation_low': cons_low,
                            'current_price': current_price,
                            'volume_increase': round(volume_increase, 2),
                            'hours_since_breakout': hours_since_breakout,
                            'pattern_type': pattern_type,
                            'confidence': round(confidence, 1),
                            'signal': signal,
                            'volume_24h': ticker['quote_volume_24h'],
                            'market_cap': market_cap_map.get(ticker['base'], None),
                            'reason': generate_breakout_reason(
                                breakout_direction, breakout_strength, cons_range_pct,
                                volume_increase, hours_since_breakout, pattern_type
                            )
                        })
                        
                        emoji = "🚀" if breakout_direction == "BULLISH" else "📉"
                        logger.info(f"{emoji} {symbol}: {breakout_direction} breakout {breakout_strength:.1f}%, range {cons_range_pct:.1f}%, vol {volume_increase:.1f}x, {hours_since_breakout}h ago")
                
                except Exception as e:
                    logger.debug(f"Error analyzing {ticker.get('symbol')}: {e}")
                    continue
                
                # Limit results
                if len(results) >= 50:
                    break
            
            # Sort by confidence
            results.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Log breakdown by direction
            bullish_count = len([r for r in results if r['breakout_direction'] == 'BULLISH'])
            bearish_count = len([r for r in results if r['breakout_direction'] == 'BEARISH'])
            logger.info(f"Found {len(results)} breakout opportunities (🚀 {bullish_count} bullish, 📉 {bearish_count} bearish)")
            
            return {
                'success': True,
                'breakouts': results[:top_n],
                'total_analyzed': len(top_candidates),
                'total_breakouts': len(results),
                'parameters': {
                    'consolidation_hours': consolidation_hours,
                    'min_breakout_pct': min_breakout_pct,
                    'min_volume_increase': min_volume_increase,
                    'max_market_cap': max_market_cap,
                    'direction': direction
                }
            }
    
    except Exception as e:
        logger.error(f"Error in breakout scanner: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


def generate_breakout_reason(direction, strength, range_pct, volume_inc, hours_ago, pattern):
    """Generate human-readable explanation for breakout"""
    reasons = []
    
    # Direction and strength
    emoji = "🚀" if direction == "BULLISH" else "📉"
    reasons.append(f"{emoji} {direction} breakout +{strength:.1f}%")
    
    # Pattern type
    if range_pct < 5:
        reasons.append(f"from tight squeeze ({range_pct:.1f}% range)")
    else:
        reasons.append(f"from {pattern.lower()} ({range_pct:.1f}% range)")
    
    # Volume confirmation
    if volume_inc > 3:
        reasons.append(f"MASSIVE volume ({volume_inc:.1f}x)")
    elif volume_inc > 2:
        reasons.append(f"strong volume ({volume_inc:.1f}x)")
    else:
        reasons.append(f"volume up {volume_inc:.1f}x")
    
    # Freshness
    if hours_ago <= 2:
        reasons.append(f"⚡ FRESH ({hours_ago}h ago)")
    elif hours_ago <= 6:
        reasons.append(f"recent ({hours_ago}h ago)")
    else:
        reasons.append(f"{hours_ago}h ago")
    
    return " • ".join(reasons)


@router.get("/api/funding-divergence")
async def get_funding_divergence(
    min_extreme: float = 0.08,  # Minimum absolute funding rate (0.08% = 8 basis points)
    min_oi_change: float = 20.0,  # Minimum open interest change %
    lookback_hours: int = 24,
    top_n: int = 5,
    max_market_cap: float = 500_000_000  # $500M default
):
    """
    Detect extreme funding rate situations for potential reversals or continuations
    
    Strategy:
    - Identifies coins with extreme funding rates (overleveraged positions)
    - Detects divergences between funding and price movement
    - Flags potential short squeezes and long liquidations
    
    Signal Types:
    1. Mean Reversion: Extreme funding + stable price → Reversal likely
    2. Momentum Continuation: Extreme funding + price moving same direction
    3. Squeeze Setup: Extreme funding + high OI + approaching liquidations
    
    Parameters:
    - min_extreme: Minimum absolute funding rate % (default 0.08)
    - min_oi_change: Minimum % change in open interest (default 20%)
    - lookback_hours: Hours to analyze (default 24)
    - top_n: Number of results to return
    - max_market_cap: Maximum market cap filter (default $500M)
    """
    logger.info("=" * 80)
    logger.info("FUNDING RATE DIVERGENCE SCANNER")
    logger.info(f"Parameters: min_extreme={min_extreme}%, min_oi_change={min_oi_change}%, lookback={lookback_hours}h")
    logger.info("=" * 80)
    
    try:
        results = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get current funding rates from Binance Futures
            logger.info("Fetching funding rates from Binance Futures...")
            funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
            funding_response = await client.get(funding_url)
            
            if funding_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch funding rates")
            
            funding_data = funding_response.json()
            
            # Step 2: Get open interest data
            logger.info("Fetching open interest data...")
            oi_url = "https://fapi.binance.com/fapi/v1/openInterest"
            
            # Filter for USDT perpetual contracts with extreme funding
            extreme_funding_pairs = []
            for item in funding_data:
                symbol = item.get('symbol', '')
                if not symbol.endswith('USDT'):
                    continue
                
                # Skip coins, stablecoins, leveraged tokens
                base = symbol.replace('USDT', '')
                skip_tokens = ['USDC', 'BUSD', 'DAI', 'TUSD', 'UP', 'DOWN', 'BULL', 'BEAR']
                if any(skip in base for skip in skip_tokens):
                    continue
                
                try:
                    last_funding_rate = float(item.get('lastFundingRate', 0)) * 100  # Convert to percentage
                    mark_price = float(item.get('markPrice', 0))
                    
                    # Check if funding is extreme
                    if abs(last_funding_rate) >= min_extreme and mark_price > 0:
                        extreme_funding_pairs.append({
                            'symbol': symbol,
                            'base': base,
                            'funding_rate': last_funding_rate,
                            'mark_price': mark_price,
                            'next_funding_time': item.get('nextFundingTime', 0)
                        })
                except (ValueError, TypeError):
                    continue
            
            logger.info(f"Found {len(extreme_funding_pairs)} pairs with extreme funding (>{min_extreme}%)")
            
            if len(extreme_funding_pairs) == 0:
                return {
                    'success': True,
                    'opportunities': [],
                    'total_analyzed': 0,
                    'total_extreme': 0,
                    'parameters': {
                        'min_extreme': min_extreme,
                        'min_oi_change': min_oi_change,
                        'lookback_hours': lookback_hours,
                        'max_market_cap': max_market_cap
                    }
                }
            
            # Step 3: Get market cap data (same as other scanners)
            market_cap_map = {}
            if max_market_cap and max_market_cap > 0:
                logger.info("Fetching market cap data from CoinGecko...")
                try:
                    coins_list_url = "https://api.coingecko.com/api/v3/coins/list"
                    coins_response = await client.get(coins_list_url)
                    
                    if coins_response.status_code == 200:
                        coins_list = coins_response.json()
                        symbol_to_id = {}
                        for coin in coins_list:
                            symbol = coin.get('symbol', '').upper()
                            coin_id = coin.get('id', '')
                            if symbol and coin_id:
                                if symbol not in symbol_to_id:
                                    symbol_to_id[symbol] = coin_id
                        
                        bases = [p['base'] for p in extreme_funding_pairs]
                        coin_ids = [symbol_to_id.get(base) for base in bases if symbol_to_id.get(base)]
                        
                        if coin_ids:
                            batch_size = 250
                            for i in range(0, len(coin_ids), batch_size):
                                batch = coin_ids[i:i+batch_size]
                                ids_param = ','.join(batch)
                                
                                market_url = "https://api.coingecko.com/api/v3/coins/markets"
                                params = {
                                    'vs_currency': 'usd',
                                    'ids': ids_param,
                                    'per_page': 250
                                }
                                
                                market_response = await client.get(market_url, params=params)
                                
                                if market_response.status_code == 200:
                                    market_data = market_response.json()
                                    for coin in market_data:
                                        symbol = coin.get('symbol', '').upper()
                                        mcap = coin.get('market_cap')
                                        if symbol and mcap:
                                            market_cap_map[symbol] = mcap
                                
                                await asyncio.sleep(0.5)
                        
                        logger.info(f"Retrieved market caps for {len(market_cap_map)} tokens")
                except Exception as e:
                    logger.warning(f"Failed to fetch market caps: {e}")
            
            # Apply market cap filter
            if max_market_cap and max_market_cap > 0 and market_cap_map:
                original_count = len(extreme_funding_pairs)
                extreme_funding_pairs = [
                    p for p in extreme_funding_pairs
                    if market_cap_map.get(p['base'], 0) <= max_market_cap or p['base'] not in market_cap_map
                ]
                logger.info(f"Market cap filter: {original_count} → {len(extreme_funding_pairs)} pairs")
            
            # Step 4: Analyze each extreme funding pair
            for pair in extreme_funding_pairs[:100]:  # Limit to top 100
                try:
                    symbol = pair['symbol']
                    base = pair['base']
                    funding_rate = pair['funding_rate']
                    
                    # Get open interest
                    oi_response = await client.get(oi_url, params={'symbol': symbol})
                    
                    if oi_response.status_code != 200:
                        continue
                    
                    oi_data = oi_response.json()
                    current_oi = float(oi_data.get('openInterest', 0))
                    
                    # Get historical klines to check price movement
                    klines_url = f"https://fapi.binance.com/fapi/v1/klines"
                    params = {
                        'symbol': symbol,
                        'interval': '1h',
                        'limit': lookback_hours + 1
                    }
                    
                    klines_response = await client.get(klines_url, params=params)
                    
                    if klines_response.status_code != 200:
                        continue
                    
                    klines = klines_response.json()
                    
                    if len(klines) < 2:
                        continue
                    
                    # Calculate price change
                    old_price = float(klines[0][4])  # Close of oldest candle
                    current_price = float(klines[-1][4])  # Close of newest candle
                    price_change_pct = ((current_price - old_price) / old_price) * 100
                    
                    # Determine signal type
                    signal_type = None
                    confidence = 0
                    
                    # Extreme funding scoring (40 points)
                    abs_funding = abs(funding_rate)
                    if abs_funding >= 0.15:
                        confidence += 40
                        extreme_level = "EXTREME"
                    elif abs_funding >= 0.10:
                        confidence += 30
                        extreme_level = "VERY_HIGH"
                    elif abs_funding >= 0.08:
                        confidence += 20
                        extreme_level = "HIGH"
                    else:
                        extreme_level = "MODERATE"
                    
                    # Divergence analysis (30 points)
                    funding_direction = "POSITIVE" if funding_rate > 0 else "NEGATIVE"
                    
                    # Mean reversion setup: Extreme funding + small price move
                    if abs_funding >= 0.10 and abs(price_change_pct) < 5:
                        signal_type = "MEAN_REVERSION"
                        confidence += 30
                        if funding_rate > 0:
                            trade_direction = "SHORT"  # Too many longs, expect reversal down
                        else:
                            trade_direction = "LONG"   # Too many shorts, expect reversal up
                    
                    # Momentum continuation: Funding and price aligned
                    elif (funding_rate > 0 and price_change_pct > 3) or (funding_rate < 0 and price_change_pct < -3):
                        signal_type = "MOMENTUM"
                        confidence += 20
                        trade_direction = "LONG" if price_change_pct > 0 else "SHORT"
                    
                    # Squeeze setup: Extreme funding opposite to price
                    elif (funding_rate < -0.10 and price_change_pct > 2):
                        signal_type = "SHORT_SQUEEZE"
                        confidence += 35
                        trade_direction = "LONG"  # Shorts getting squeezed
                    elif (funding_rate > 0.10 and price_change_pct < -2):
                        signal_type = "LONG_LIQUIDATION"
                        confidence += 35
                        trade_direction = "SHORT"  # Longs getting liquidated
                    else:
                        signal_type = "MONITORING"
                        confidence += 10
                        trade_direction = "LONG" if funding_rate < 0 else "SHORT"
                    
                    # Open interest consideration (20 points)
                    # Since we don't have historical OI, give moderate score
                    if current_oi > 0:
                        confidence += 15
                    
                    # Volatility bonus (10 points)
                    if abs(price_change_pct) > 10:
                        confidence += 10
                    elif abs(price_change_pct) > 5:
                        confidence += 5
                    
                    confidence = min(100, confidence)
                    
                    # Signal strength classification
                    if confidence > 80:
                        signal = "VERY_STRONG"
                    elif confidence > 65:
                        signal = "STRONG"
                    elif confidence > 50:
                        signal = "MEDIUM"
                    else:
                        signal = "WEAK"
                    
                    # Only include if meets minimum confidence
                    if confidence >= 50:
                        results.append({
                            'symbol': symbol,
                            'base': base,
                            'funding_rate': round(funding_rate, 4),
                            'funding_direction': funding_direction,
                            'extreme_level': extreme_level,
                            'price_change_24h': round(price_change_pct, 2),
                            'current_price': current_price,
                            'open_interest': current_oi,
                            'signal_type': signal_type,
                            'trade_direction': trade_direction,
                            'confidence': round(confidence, 1),
                            'signal': signal,
                            'market_cap': market_cap_map.get(base, None),
                            'reason': generate_funding_reason(
                                funding_rate, signal_type, price_change_pct, 
                                extreme_level, trade_direction
                            )
                        })
                        
                        logger.info(f"✓ {symbol}: {signal_type} - Funding {funding_rate:.3f}%, Price {price_change_pct:+.1f}%, {trade_direction}")
                
                except Exception as e:
                    logger.debug(f"Error analyzing {pair.get('symbol')}: {e}")
                    continue
            
            # Sort by confidence
            results.sort(key=lambda x: x['confidence'], reverse=True)
            
            logger.info(f"Found {len(results)} funding divergence opportunities")
            
            return {
                'success': True,
                'opportunities': results[:top_n],
                'total_analyzed': len(extreme_funding_pairs),
                'total_extreme': len(results),
                'parameters': {
                    'min_extreme': min_extreme,
                    'min_oi_change': min_oi_change,
                    'lookback_hours': lookback_hours,
                    'max_market_cap': max_market_cap
                }
            }
    
    except Exception as e:
        logger.error(f"Error in funding divergence scanner: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


def generate_funding_reason(funding_rate, signal_type, price_change, extreme_level, trade_direction):
    """Generate human-readable explanation for funding divergence"""
    reasons = []
    
    # Funding indicator
    if funding_rate > 0:
        reasons.append(f"📈 Longs paying {abs(funding_rate):.3f}%")
    else:
        reasons.append(f"📉 Shorts paying {abs(funding_rate):.3f}%")
    
    # Signal type with emoji
    signal_emojis = {
        'MEAN_REVERSION': '🔄',
        'MOMENTUM': '⚡',
        'SHORT_SQUEEZE': '🚀',
        'LONG_LIQUIDATION': '💥',
        'MONITORING': '👀'
    }
    emoji = signal_emojis.get(signal_type, '📊')
    
    # Signal explanation
    if signal_type == 'MEAN_REVERSION':
        reasons.append(f"{emoji} Overleveraged - price stable ({price_change:+.1f}%)")
    elif signal_type == 'MOMENTUM':
        reasons.append(f"{emoji} Strong momentum ({price_change:+.1f}%)")
    elif signal_type == 'SHORT_SQUEEZE':
        reasons.append(f"{emoji} SHORT SQUEEZE building - price rising {price_change:+.1f}%")
    elif signal_type == 'LONG_LIQUIDATION':
        reasons.append(f"{emoji} LONG LIQUIDATION risk - price falling {price_change:+.1f}%")
    else:
        reasons.append(f"{emoji} Monitor - price {price_change:+.1f}%")
    
    # Trade direction
    if trade_direction == "LONG":
        reasons.append("→ LONG opportunity")
    else:
        reasons.append("→ SHORT opportunity")
    
    return " • ".join(reasons)


@router.get("/api/big-mover-score")
async def get_big_mover_score(
    min_score: float = 70.0,
    max_market_cap: float = 500_000_000,
    top_n: int = 10
):
    """
    Composite Big Mover Score - Combines all signals for ultimate accuracy
    
    Aggregates scores from:
    1. Volume Surge Detection (30% weight)
    2. Breakout Scanner (30% weight)
    3. Funding Rate Divergence (20% weight)
    4. Price Momentum (20% weight)
    
    Returns only coins with composite score >= min_score (70 default)
    """
    logger.info("=" * 80)
    logger.info("COMPOSITE BIG MOVER SCORE")
    logger.info(f"Parameters: min_score={min_score}, max_mcap=${max_market_cap/1_000_000:.0f}M")
    logger.info("=" * 80)
    
    try:
        composite_results = []
        current_time = time.time()
        
        # Instead of HTTP calls, directly call the scanner functions (much faster!)
        logger.info("Fetching all signal types (direct function calls)...")
        
        # Check cache first and build tasks for uncached data
        fetch_tasks = []
        cache_keys = []
        
        # Volume surges - check cache
        if _scanner_cache['volume_surges']['data'] and (current_time - _scanner_cache['volume_surges']['timestamp']) < CACHE_TTL:
            logger.info("Using cached volume surges data")
            volume_data = _scanner_cache['volume_surges']['data']
        else:
            fetch_tasks.append(get_volume_surges(top_n=50))
            cache_keys.append('volume_surges')
            volume_data = None
        
        # Breakouts - check cache
        if _scanner_cache['breakouts']['data'] and (current_time - _scanner_cache['breakouts']['timestamp']) < CACHE_TTL:
            logger.info("Using cached breakout data")
            breakout_data = _scanner_cache['breakouts']['data']
        else:
            fetch_tasks.append(get_breakout_opportunities(max_market_cap=max_market_cap, top_n=50))
            cache_keys.append('breakouts')
            breakout_data = None
        
        # Funding - check cache
        if _scanner_cache['funding']['data'] and (current_time - _scanner_cache['funding']['timestamp']) < CACHE_TTL:
            logger.info("Using cached funding data")
            funding_data = _scanner_cache['funding']['data']
        else:
            fetch_tasks.append(get_funding_divergence(min_extreme=0.05, max_market_cap=max_market_cap, top_n=50))
            cache_keys.append('funding')
            funding_data = None
        
        # Fetch all uncached data in parallel
        if fetch_tasks:
            logger.info(f"Fetching {len(fetch_tasks)} scanner(s) in parallel...")
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            # Process results and update cache
            for i, key in enumerate(cache_keys):
                if isinstance(results[i], Exception):
                    logger.error(f"Error fetching {key}: {results[i]}")
                    continue
                
                if key == 'volume_surges':
                    volume_data = results[i]
                    _scanner_cache['volume_surges']['data'] = volume_data
                    _scanner_cache['volume_surges']['timestamp'] = current_time
                    logger.info(f"Cached {len(volume_data.get('surges', []))} volume surges")
                elif key == 'breakouts':
                    breakout_data = results[i]
                    _scanner_cache['breakouts']['data'] = breakout_data
                    _scanner_cache['breakouts']['timestamp'] = current_time
                    logger.info(f"Cached {len(breakout_data.get('breakouts', []))} breakouts")
                elif key == 'funding':
                    funding_data = results[i]
                    _scanner_cache['funding']['data'] = funding_data
                    _scanner_cache['funding']['timestamp'] = current_time
                    logger.info(f"Cached {len(funding_data.get('divergences', []))} funding signals")
        
        # Use empty dicts if still None (shouldn't happen, but safety)
        volume_data = volume_data or {'surges': []}
        breakout_data = breakout_data or {'breakouts': []}
        funding_data = funding_data or {'divergences': []}
        
        logger.info(f"Got {len(volume_data.get('surges', []))} volume surges, {len(breakout_data.get('breakouts', []))} breakouts, {len(funding_data.get('divergences', []))} funding signals")
        
        # Create symbol-indexed maps
        volume_map = {s['symbol']: s for s in volume_data.get('surges', [])}
        breakout_map = {b['symbol']: b for b in breakout_data.get('breakouts', [])}
        funding_map = {f['symbol']: f for f in funding_data.get('divergences', [])}
        
        # Get all unique symbols
        all_symbols = set(list(volume_map.keys()) + list(breakout_map.keys()) + list(funding_map.keys()))
        logger.info(f"Analyzing {len(all_symbols)} unique symbols across all signals")
        
        # Calculate composite scores
        for symbol in all_symbols:
            # Get individual scores (0-100 scale)
            volume_score = 0
            breakout_score = 0
            funding_score = 0
            momentum_score = 0
            
            # Volume surge contribution (30%)
            if symbol in volume_map:
                v = volume_map[symbol]
                volume_score = v.get('confidence', 0) * 0.30
            
            # Breakout contribution (30%)
            if symbol in breakout_map:
                b = breakout_map[symbol]
                breakout_score = b.get('confidence', 0) * 0.30
            
            # Funding divergence contribution (20%)
            if symbol in funding_map:
                f = funding_map[symbol]
                funding_score = f.get('confidence', 0) * 0.20
            
            # Momentum score from price action (20%)
            price_change_24h = 0
            if symbol in volume_map:
                price_change_24h = volume_map[symbol].get('price_change_24h', 0)
            elif symbol in breakout_map:
                price_change_24h = breakout_map[symbol].get('breakout_strength', 0)
            
            # Momentum scoring
            if abs(price_change_24h) > 10:
                momentum_score = 100 * 0.20
            elif abs(price_change_24h) > 5:
                momentum_score = 70 * 0.20
            elif abs(price_change_24h) > 2:
                momentum_score = 40 * 0.20
            else:
                momentum_score = 20 * 0.20
            
            # Calculate composite score
            composite_score = volume_score + breakout_score + funding_score + momentum_score
            
            # Filter by minimum score
            if composite_score < min_score:
                continue
            
            # Determine overall signal
            signal_count = sum([
                1 if symbol in volume_map else 0,
                1 if symbol in breakout_map else 0,
                1 if symbol in funding_map else 0
            ])
            
            if signal_count >= 3:
                overall_signal = "VERY_STRONG"
            elif signal_count >= 2:
                overall_signal = "STRONG"
            elif composite_score >= 80:
                overall_signal = "STRONG"
            elif composite_score >= 70:
                overall_signal = "MEDIUM"
            else:
                overall_signal = "WEAK"
            
            # Collect signal details
            active_signals = []
            if symbol in volume_map:
                active_signals.append(f"Volume: {volume_map[symbol]['signal']}")
            if symbol in breakout_map:
                active_signals.append(f"Breakout: {breakout_map[symbol]['signal']}")
            if symbol in funding_map:
                active_signals.append(f"Funding: {funding_map[symbol]['signal']}")
            
            # Get base asset
            base = symbol.replace('USDT', '').replace('PERP', '')
            
            # Get market cap
            market_cap = None
            if symbol in volume_map:
                market_cap = volume_map[symbol].get('market_cap')
            elif symbol in breakout_map:
                market_cap = breakout_map[symbol].get('market_cap')
            
            # Build composite result
            composite_results.append({
                'symbol': symbol,
                'base': base,
                'composite_score': round(composite_score, 1),
                'signal': overall_signal,
                'signal_count': signal_count,
                'active_signals': active_signals,
                'breakdown': {
                    'volume_contribution': round(volume_score, 1),
                    'breakout_contribution': round(breakout_score, 1),
                    'funding_contribution': round(funding_score, 1),
                    'momentum_contribution': round(momentum_score, 1)
                },
                'individual_scores': {
                    'volume_surge': volume_map.get(symbol, {}).get('confidence', 0) if symbol in volume_map else None,
                    'breakout': breakout_map.get(symbol, {}).get('confidence', 0) if symbol in breakout_map else None,
                    'funding_divergence': funding_map.get(symbol, {}).get('confidence', 0) if symbol in funding_map else None
                },
                'market_cap': market_cap,
                'price_change_24h': price_change_24h,
                'reason': generate_composite_reason(composite_score, signal_count, active_signals, price_change_24h)
            })
            
            # Sort by composite score
            composite_results.sort(key=lambda x: x['composite_score'], reverse=True)
            
            logger.info(f"Found {len(composite_results)} coins scoring >= {min_score}")
            
            return {
                'success': True,
                'movers': composite_results[:top_n],
                'total_analyzed': len(all_symbols),
                'total_qualified': len(composite_results),
                'parameters': {
                    'min_score': min_score,
                    'max_market_cap': max_market_cap,
                    'weights': {
                        'volume_surge': '30%',
                        'breakout': '30%',
                        'funding_divergence': '20%',
                        'momentum': '20%'
                    }
                }
            }
    
    except Exception as e:
        logger.error(f"Error in composite big mover score: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


def generate_composite_reason(score, signal_count, active_signals, price_change):
    """Generate human-readable explanation for composite score"""
    reasons = []
    
    # Overall strength
    if score >= 90:
        reasons.append("🔥 ULTIMATE signal")
    elif score >= 80:
        reasons.append("💎 Excellent opportunity")
    elif score >= 70:
        reasons.append("✨ Strong signal")
    else:
        reasons.append("📊 Moderate signal")
    
    # Signal convergence
    if signal_count >= 3:
        reasons.append(f"ALL {signal_count} scanners aligned")
    elif signal_count >= 2:
        reasons.append(f"{signal_count} scanners confirm")
    else:
        reasons.append("Single strong signal")
    
    # Active signals
    if active_signals:
        reasons.append(" + ".join(active_signals))
    
    # Momentum
    if price_change > 10:
        reasons.append(f"Strong momentum (+{price_change:.1f}%)")
    elif price_change > 5:
        reasons.append(f"Building momentum (+{price_change:.1f}%)")
    elif price_change < -5:
        reasons.append(f"Pullback opportunity ({price_change:.1f}%)")
    
    return " | ".join(reasons)


@router.get("/api/symbol-signals/{symbol}")
async def get_symbol_signals(symbol: str):
    """
    Get all available signals for a specific trading pair
    
    Returns volume surge, breakout, and funding data for the requested symbol.
    Symbol should be in format like 'BTCUSDT', 'ETHUSDT', etc.
    """
    logger.info(f"Fetching signals for symbol: {symbol}")
    
    try:
        result = {
            "symbol": symbol,
            "volume_surge": None,
            "breakout": None,
            "funding_divergence": None,
            "timestamp": time.time()
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Check Volume Surge
            try:
                logger.info(f"Analyzing volume surge for {symbol}...")
                
                # Get 24h ticker
                ticker_url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
                ticker_resp = await client.get(ticker_url)
                
                if ticker_resp.status_code == 200:
                    ticker = ticker_resp.json()
                    current_volume_usdt = float(ticker.get('quoteVolume', 0))
                    price_change_pct = float(ticker.get('priceChangePercent', 0))
                    
                    # Get historical klines to calculate average volume
                    klines_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=168"
                    klines_resp = await client.get(klines_url)
                    
                    if klines_resp.status_code == 200:
                        klines = klines_resp.json()
                        if len(klines) > 0:
                            volumes = [float(k[7]) for k in klines]  # Quote asset volume
                            avg_volume = sum(volumes) / len(volumes)
                            
                            if avg_volume > 0:
                                surge_pct = ((current_volume_usdt / avg_volume) - 1) * 100
                                
                                # Determine signal strength
                                if surge_pct >= 300:
                                    signal = "VERY_STRONG"
                                elif surge_pct >= 200:
                                    signal = "STRONG"
                                elif surge_pct >= 100:
                                    signal = "MEDIUM"
                                else:
                                    signal = "WEAK"
                                
                                result["volume_surge"] = {
                                    "symbol": symbol,
                                    "current_volume_usd": current_volume_usdt,
                                    "avg_volume_usd": avg_volume,
                                    "volume_surge_percentage": surge_pct,
                                    "price_change_24h": price_change_pct,
                                    "signal": signal,
                                    "reason": f"Volume is {surge_pct:.1f}% above 7-day average"
                                }
            except Exception as e:
                logger.warning(f"Volume surge analysis failed for {symbol}: {e}")
            
            # 2. Check Breakout
            try:
                logger.info(f"Analyzing breakout for {symbol}...")
                
                # Get 4h klines for breakout analysis
                klines_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=72"
                klines_resp = await client.get(klines_url)
                
                if klines_resp.status_code == 200:
                    klines = klines_resp.json()
                    if len(klines) >= 20:
                        closes = [float(k[4]) for k in klines]
                        highs = [float(k[2]) for k in klines]
                        lows = [float(k[3]) for k in klines]
                        volumes = [float(k[7]) for k in klines]
                        
                        current_price = closes[-1]
                        recent_high = max(highs[-20:])
                        recent_low = min(lows[-20:])
                        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
                        current_volume = volumes[-1]
                        
                        # Calculate price range and position
                        price_range = recent_high - recent_low
                        if price_range > 0:
                            position_in_range = ((current_price - recent_low) / price_range) * 100
                            
                            # Check for breakout
                            volume_increase = (current_volume / avg_volume) if avg_volume > 0 else 0
                            
                            breakout_score = 0
                            direction = "NEUTRAL"
                            
                            # More lenient breakout detection - show any significant price position with volume
                            if position_in_range > 80:  # In upper 20% of range
                                if volume_increase > 1.2:  # Any volume increase
                                    breakout_score = min(100, position_in_range * (volume_increase ** 0.5) * 10)
                                    direction = "LONG"
                                else:
                                    # Still show but with lower score if no volume
                                    breakout_score = position_in_range * 0.8
                                    direction = "LONG"
                            elif position_in_range < 20:  # In lower 20% of range  
                                if volume_increase > 1.2:
                                    breakout_score = min(100, (100 - position_in_range) * (volume_increase ** 0.5) * 10)
                                    direction = "SHORT"
                                else:
                                    breakout_score = (100 - position_in_range) * 0.8
                                    direction = "SHORT"
                            else:
                                # Middle of range - neutral
                                direction = "NEUTRAL"
                                breakout_score = 0
                            
                            # Always show breakout data if score > 0 (even weak signals)
                            if breakout_score > 0 or direction != "NEUTRAL":
                                # Get 24h price change
                                ticker_url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
                                ticker_resp = await client.get(ticker_url)
                                price_change_24h = 0
                                if ticker_resp.status_code == 200:
                                    price_change_24h = float(ticker_resp.json().get('priceChangePercent', 0))
                                
                                # Build reason
                                if volume_increase > 1.5:
                                    reason = f"{direction} breakout with {volume_increase:.1f}x volume - Strong signal"
                                elif volume_increase > 1.2:
                                    reason = f"{direction} setup with {volume_increase:.1f}x volume - Moderate signal"
                                else:
                                    reason = f"{direction} position at {position_in_range:.1f}% of range - Watch for volume"
                                
                                result["breakout"] = {
                                    "symbol": symbol,
                                    "current_price": current_price,
                                    "breakout_score": breakout_score,
                                    "direction": direction,
                                    "price_change_24h": price_change_24h,
                                    "volume_increase": volume_increase,
                                    "position_in_range": position_in_range,
                                    "reason": reason
                                }
            except Exception as e:
                logger.warning(f"Breakout analysis failed for {symbol}: {e}")
            
            # 3. Check Funding Rate Divergence
            try:
                logger.info(f"Analyzing funding rate for {symbol}...")
                
                # Get funding rate from Binance Futures
                funding_url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
                funding_resp = await client.get(funding_url)
                
                if funding_resp.status_code == 200:
                    funding_data = funding_resp.json()
                    funding_rate = float(funding_data.get('lastFundingRate', 0))
                    mark_price = float(funding_data.get('markPrice', 0))
                    
                    # Get open interest
                    oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
                    oi_resp = await client.get(oi_url)
                    
                    open_interest = 0
                    if oi_resp.status_code == 200:
                        open_interest = float(oi_resp.json().get('openInterest', 0))
                    
                    # Calculate divergence score based on funding rate extremity
                    abs_funding_pct = abs(funding_rate) * 100
                    divergence_score = min(100, abs_funding_pct * 1000)  # Scale to 0-100
                    
                    if divergence_score > 10:  # Only report significant divergences
                        result["funding_divergence"] = {
                            "symbol": symbol,
                            "binance_funding_rate": funding_rate,
                            "other_funding_rate": funding_rate,  # Using same for now
                            "divergence_percentage": abs_funding_pct,
                            "divergence_score": divergence_score,
                            "mark_price": mark_price,
                            "open_interest": open_interest,
                            "reason": f"{'Extreme positive' if funding_rate > 0 else 'Extreme negative'} funding rate at {abs_funding_pct:.4f}%"
                        }
            except Exception as e:
                logger.warning(f"Funding rate analysis failed for {symbol}: {e}")
        
        logger.info(f"Symbol signals complete for {symbol}")
        return {
            "success": True,
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error fetching signals for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/reversal-scanner")
async def get_reversal_scanner(
    min_score: float = 60.0,
    top_n: int = 20,
    max_market_cap: float = 500_000_000
):
    """
    Scan all symbols for potential bottoms and tops
    
    Returns symbols with high reversal probability scores
    """
    logger.info(f"Scanning for reversals: min_score={min_score}, top_n={top_n}")
    
    try:
        results = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get all USDT pairs
            exchange_info_url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
            exchange_response = await client.get(exchange_info_url)
            
            if exchange_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch symbols")
            
            exchange_data = exchange_response.json()
            symbols = [s['symbol'] for s in exchange_data['symbols'] 
                      if s['status'] == 'TRADING' and 
                      s['contractType'] == 'PERPETUAL' and 
                      s['symbol'].endswith('USDT')]
            
            logger.info(f"Found {len(symbols)} total symbols")
            
            # Scan each symbol (limit to top 50 like other scanners)
            symbols_to_scan = symbols[:50]
            logger.info(f"Scanning top {len(symbols_to_scan)} symbols for reversals")
            
            for symbol in symbols_to_scan:
                try:
                    # Call the reversal detection for this symbol
                    reversal_data = await get_reversal_detection(symbol)
                    
                    if reversal_data['success']:
                        data = reversal_data['data']
                        
                        # Check if either bottom or top signal meets threshold
                        has_bottom = data['bottom_signal'] and data['bottom_signal']['score'] >= min_score
                        has_top = data['top_signal'] and data['top_signal']['score'] >= min_score
                        
                        if has_bottom or has_top:
                            results.append(data)
                            
                except Exception as e:
                    logger.debug(f"Skipping {symbol}: {e}")
                    continue
            
            # Sort by highest score (either bottom or top)
            results.sort(key=lambda x: max(
                x['bottom_signal']['score'] if x['bottom_signal'] else 0,
                x['top_signal']['score'] if x['top_signal'] else 0
            ), reverse=True)
            
            # Limit results
            results = results[:top_n]
            
            logger.info(f"Found {len(results)} reversal opportunities")
            
            return {
                "success": True,
                "reversals": results,
                "total_scanned": len(symbols_to_scan),
                "parameters": {
                    "min_score": min_score,
                    "max_market_cap": max_market_cap
                }
            }
            
    except Exception as e:
        logger.error(f"Error in reversal scanner: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/reversal-detection/{symbol}")
async def get_reversal_detection(symbol: str):
    """
    Detect potential bottoms (buy opportunities) or tops (sell signals)
    
    Uses multiple indicators:
    - RSI (oversold < 30, overbought > 70)
    - Price vs Moving Averages (20, 50, 200 MA)
    - Volume spikes (capitulation/exhaustion)
    - Bollinger Bands (price extremes)
    - Recent price action patterns
    
    Returns a score from 0-100 for both BOTTOM and TOP probability
    """
    logger.info(f"Analyzing reversal potential for {symbol}")
    
    try:
        result = {
            "symbol": symbol,
            "bottom_signal": None,
            "top_signal": None,
            "timestamp": time.time()
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try futures first, then fall back to spot
            # Get 12h klines for comprehensive analysis (200 periods for 200 MA)
            
            # Try futures endpoint first (USDT-M)
            klines_url_futures = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=12h&limit=200"
            klines_resp = await client.get(klines_url_futures)
            
            # If futures fails, try spot
            if klines_resp.status_code != 200:
                logger.info(f"Futures endpoint failed for {symbol}, trying spot")
                klines_url_spot = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=12h&limit=200"
                klines_resp = await client.get(klines_url_spot)
            
            if klines_resp.status_code != 200:
                logger.warning(f"Failed to fetch klines for {symbol} from both futures and spot")
                return {"success": False, "error": "Failed to fetch price data"}
            
            klines = klines_resp.json()
            if len(klines) < 50:
                logger.warning(f"Insufficient data for {symbol}")
                return {"success": False, "error": "Insufficient price data"}
            
            # Extract OHLCV data
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            volumes = [float(k[7]) for k in klines]  # Quote volume
            
            current_price = closes[-1]
            current_volume = volumes[-1]
            
            # Calculate indicators
            # 1. RSI (14 period)
            def calculate_rsi(prices, period=14):
                deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
                gains = [d if d > 0 else 0 for d in deltas]
                losses = [-d if d < 0 else 0 for d in deltas]
                
                avg_gain = sum(gains[-period:]) / period
                avg_loss = sum(losses[-period:]) / period
                
                if avg_loss == 0:
                    return 100
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                return rsi
            
            rsi = calculate_rsi(closes)
            
            # 2. Moving Averages
            ma_20 = sum(closes[-20:]) / 20
            ma_50 = sum(closes[-50:]) / 50
            ma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sum(closes) / len(closes)
            
            # 3. Bollinger Bands (20 period, 2 std dev)
            sma_20 = ma_20
            std_dev = (sum([(c - sma_20) ** 2 for c in closes[-20:]]) / 20) ** 0.5
            upper_band = sma_20 + (2 * std_dev)
            lower_band = sma_20 - (2 * std_dev)
            
            # 4. Volume analysis
            avg_volume = sum(volumes[-20:]) / 20
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 5. Recent price action
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
            price_range = recent_high - recent_low
            position_in_range = ((current_price - recent_low) / price_range * 100) if price_range > 0 else 50
            
            # Distance from MAs
            dist_from_ma20 = ((current_price - ma_20) / ma_20 * 100)
            dist_from_ma50 = ((current_price - ma_50) / ma_50 * 100)
            dist_from_ma200 = ((current_price - ma_200) / ma_200 * 100)
            
            # BOTTOM DETECTION LOGIC
            bottom_score = 0
            bottom_reasons = []
            
            # RSI oversold
            if rsi < 30:
                bottom_score += 30
                bottom_reasons.append(f"RSI extremely oversold ({rsi:.1f})")
            elif rsi < 40:
                bottom_score += 20
                bottom_reasons.append(f"RSI oversold ({rsi:.1f})")
            
            # Price below lower Bollinger Band
            if current_price < lower_band:
                bb_deviation = ((lower_band - current_price) / current_price * 100)
                bottom_score += min(25, bb_deviation * 5)
                bottom_reasons.append(f"Price {bb_deviation:.1f}% below lower BB")
            
            # Deep below moving averages (potential capitulation)
            if dist_from_ma20 < -10:
                bottom_score += 15
                bottom_reasons.append(f"{abs(dist_from_ma20):.1f}% below 20 MA")
            if dist_from_ma50 < -15:
                bottom_score += 15
                bottom_reasons.append(f"{abs(dist_from_ma50):.1f}% below 50 MA")
            
            # Low position in recent range
            if position_in_range < 20:
                bottom_score += 15
                bottom_reasons.append(f"Price at {position_in_range:.0f}% of recent range (near lows)")
            
            # Volume spike (possible capitulation)
            if volume_ratio > 2.0:
                bottom_score += 10
                bottom_reasons.append(f"Volume spike {volume_ratio:.1f}x average (capitulation?)")
            
            # Check for higher lows pattern (reversal confirmation)
            if len(lows) >= 10:
                recent_lows = lows[-10:]
                if recent_lows[-1] > recent_lows[-5] and recent_lows[-5] > recent_lows[-10]:
                    bottom_score += 10
                    bottom_reasons.append("Higher lows pattern detected")
            
            # TOP DETECTION LOGIC
            top_score = 0
            top_reasons = []
            
            # RSI overbought
            if rsi > 70:
                top_score += 30
                top_reasons.append(f"RSI extremely overbought ({rsi:.1f})")
            elif rsi > 60:
                top_score += 20
                top_reasons.append(f"RSI overbought ({rsi:.1f})")
            
            # Price above upper Bollinger Band
            if current_price > upper_band:
                bb_deviation = ((current_price - upper_band) / current_price * 100)
                top_score += min(25, bb_deviation * 5)
                top_reasons.append(f"Price {bb_deviation:.1f}% above upper BB")
            
            # Extended above moving averages
            if dist_from_ma20 > 10:
                top_score += 15
                top_reasons.append(f"{dist_from_ma20:.1f}% above 20 MA")
            if dist_from_ma50 > 15:
                top_score += 15
                top_reasons.append(f"{dist_from_ma50:.1f}% above 50 MA")
            
            # High position in recent range
            if position_in_range > 80:
                top_score += 15
                top_reasons.append(f"Price at {position_in_range:.0f}% of recent range (near highs)")
            
            # Volume exhaustion
            if volume_ratio > 2.0 and dist_from_ma20 > 5:
                top_score += 10
                top_reasons.append(f"Volume spike {volume_ratio:.1f}x with extension (exhaustion?)")
            
            # Check for lower highs pattern (reversal confirmation)
            if len(highs) >= 10:
                recent_highs = highs[-10:]
                if recent_highs[-1] < recent_highs[-5] and recent_highs[-5] < recent_highs[-10]:
                    top_score += 10
                    top_reasons.append("Lower highs pattern detected")
            
            # Cap scores at 100
            bottom_score = min(100, bottom_score)
            top_score = min(100, top_score)
            
            # Determine signal strength
            def get_signal_strength(score):
                if score >= 70:
                    return "VERY_STRONG"
                elif score >= 50:
                    return "STRONG"
                elif score >= 30:
                    return "MEDIUM"
                else:
                    return "WEAK"
            
            # Only include if score is significant
            if bottom_score >= 30:
                result["bottom_signal"] = {
                    "symbol": symbol,
                    "score": bottom_score,
                    "signal": get_signal_strength(bottom_score),
                    "rsi": rsi,
                    "current_price": current_price,
                    "ma_20": ma_20,
                    "ma_50": ma_50,
                    "ma_200": ma_200,
                    "lower_band": lower_band,
                    "position_in_range": position_in_range,
                    "volume_ratio": volume_ratio,
                    "dist_from_ma20_pct": dist_from_ma20,
                    "reasons": bottom_reasons,
                    "recommendation": "POTENTIAL BOTTOM - Consider buying" if bottom_score >= 60 else "Watch for bottom formation"
                }
            
            if top_score >= 30:
                result["top_signal"] = {
                    "symbol": symbol,
                    "score": top_score,
                    "signal": get_signal_strength(top_score),
                    "rsi": rsi,
                    "current_price": current_price,
                    "ma_20": ma_20,
                    "ma_50": ma_50,
                    "ma_200": ma_200,
                    "upper_band": upper_band,
                    "position_in_range": position_in_range,
                    "volume_ratio": volume_ratio,
                    "dist_from_ma20_pct": dist_from_ma20,
                    "reasons": top_reasons,
                    "recommendation": "POTENTIAL TOP - Consider selling" if top_score >= 60 else "Watch for top formation"
                }
        
        logger.info(f"Reversal analysis complete for {symbol}: Bottom={bottom_score}, Top={top_score}")
        return {
            "success": True,
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error in reversal detection for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
