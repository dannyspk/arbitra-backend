"""
Test script to check market cap data from LunarCrush
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Make sure the env var is set before importing
if not os.getenv("LUNARCRUSH_API_KEY"):
    print("ERROR: LUNARCRUSH_API_KEY not found in .env")
    exit(1)

from src.arbitrage.api.social_sentiment import fetch_lunarcrush_data

async def test_marketcaps():
    # Test with some coins from the sample (add BTC first to verify API is working)
    test_symbols = ["BTC", "ETH", "ENS", "VIRTUAL", "POL", "PLUME", "NEIRO", "PIVX", "PNUT", "ZRO", "AR", "HOOK", "VANA", "CKB", "BANANA", "BABY", "AXL", "BMT", "HUMA", "ONE"]
    
    print("\n" + "="*80)
    print("Testing Market Cap Data from LunarCrush")
    print("="*80)
    
    for symbol in test_symbols:
        try:
            data = await fetch_lunarcrush_data(symbol)
            if data:
                coin_data = data.get('coin', {})
                market_cap = coin_data.get('market_cap', 0)
                price = coin_data.get('price', 0)
                
                if market_cap:
                    in_range = "✓ IN RANGE" if 1_000_000 <= market_cap <= 500_000_000 else "✗ OUT OF RANGE"
                    print(f"{symbol:10s} | ${market_cap/1e6:>10.2f}M | ${price:>12.8f} | {in_range}")
                else:
                    print(f"{symbol:10s} | NO MARKET CAP DATA")
            else:
                print(f"{symbol:10s} | NO DATA RETURNED")
        except Exception as e:
            print(f"{symbol:10s} | ERROR: {e}")
        
        await asyncio.sleep(0.2)  # Rate limit

if __name__ == "__main__":
    asyncio.run(test_marketcaps())
