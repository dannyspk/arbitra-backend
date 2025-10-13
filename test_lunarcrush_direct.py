"""
Direct test of LunarCrush API without using our wrapper
"""
import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")

async def test_direct():
    if not LUNARCRUSH_API_KEY:
        print("ERROR: LUNARCRUSH_API_KEY not found")
        return
    
    print(f"API Key: {LUNARCRUSH_API_KEY[:15]}...")
    
    headers = {
        "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
        "Content-Type": "application/json"
    }
    
    symbols = ["BTC", "ETH", "ENS"]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for symbol in symbols:
            print(f"\n{'='*80}")
            print(f"Testing {symbol}")
            print('='*80)
            
            coin_url = f"https://lunarcrush.com/api4/public/coins/{symbol}/v1"
            topic_url = f"https://lunarcrush.com/api4/public/topic/{symbol}/v1"
            
            # Test coin endpoint
            try:
                resp = await client.get(coin_url, headers=headers)
                print(f"Coin endpoint status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if 'data' in data:
                        mc = data['data'].get('market_cap', 'N/A')
                        print(f"Market cap: ${mc}")
                    else:
                        print(f"Response: {data}")
                else:
                    print(f"Error: {resp.text}")
            except Exception as e:
                print(f"Exception on coin endpoint: {e}")
            
            # Test topic endpoint  
            try:
                resp = await client.get(topic_url, headers=headers)
                print(f"Topic endpoint status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if 'data' in data:
                        rank = data['data'].get('topic_rank', 'N/A')
                        print(f"Topic rank: {rank}")
                    else:
                        print(f"Response: {data}")
                else:
                    print(f"Error: {resp.text}")
            except Exception as e:
                print(f"Exception on topic endpoint: {e}")

if __name__ == "__main__":
    asyncio.run(test_direct())
