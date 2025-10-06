"""
Social sentiment endpoint using LunarCrush API
"""
import os
import logging
from typing import Optional, Dict, Any
import requests
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# Get LunarCrush API key from environment
LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")


def get_lunarcrush_symbol(symbol: str) -> str:
    """
    Map trading symbols to LunarCrush symbols (usually just remove USDT/BUSD suffix)
    """
    # Remove common suffixes
    base_symbol = symbol.replace('USDT', '').replace('BUSD', '').replace('USD', '').replace('PERP', '')
    return base_symbol.upper()


def fetch_lunarcrush_data(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch social sentiment data from LunarCrush API
    Uses both /coins and /topic endpoints for comprehensive data
    """
    if not LUNARCRUSH_API_KEY:
        logger.warning("LunarCrush API key not configured")
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Get basic coin data (galaxy score, alt rank)
        coin_url = f"https://lunarcrush.com/api4/public/coins/{symbol}/v1"
        coin_response = requests.get(coin_url, headers=headers, timeout=10)
        
        # Get social/topic data (tweets, sentiment, interactions)
        topic_url = f"https://lunarcrush.com/api4/public/topic/{symbol}/v1"
        topic_response = requests.get(topic_url, headers=headers, timeout=10)
        
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
        
        # Fetch data from LunarCrush
        data = fetch_lunarcrush_data(base_symbol)
        
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
