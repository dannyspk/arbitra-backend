"""
Test script for LunarCrush API integration
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")

print(">> \nAPI Key:", LUNARCRUSH_API_KEY[:10] + "..." if len(LUNARCRUSH_API_KEY) > 10 else "NOT FOUND")

headers = {
    "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
    "Content-Type": "application/json"
}

if not LUNARCRUSH_API_KEY:
    print("\n❌ LunarCrush API key not found in .env file")
    print("Please add LUNARCRUSH_API_KEY=your_key_here to .env")
    exit(1)

# Test with BTC - try different endpoints
symbol = "BTC"

# Try the time series endpoint which should have social data
endpoints = [
    f"https://lunarcrush.com/api4/public/coins/{symbol}/v1",  # Basic coin data
    f"https://lunarcrush.com/api4/public/coins/{symbol}/time-series/v1?bucket=day&interval=1d",  # Time series
    f"https://lunarcrush.com/api4/public/topic/{symbol}/v1",  # Topic/Social data
]

for endpoint_url in endpoints:
    print(f"\n{'='*80}")
    print(f"Testing endpoint: {endpoint_url}")
    print('='*80)
    
    try:
        response = requests.get(endpoint_url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse keys: {list(data.keys())}")
            
            import json
            print(f"\nFull response:")
            print(json.dumps(data, indent=2)[:2000])  # First 2000 chars
        else:
            print(f"Error: {response.text[:500]}")
            
    except Exception as e:
        print(f"Exception: {e}")
    
    print()
