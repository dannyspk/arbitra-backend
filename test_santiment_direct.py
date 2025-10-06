"""
Direct test of Santiment API
"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env
load_dotenv()

SANTIMENT_API_KEY = os.getenv("SANTIMENT_API_KEY", "")
print(f"API Key: {SANTIMENT_API_KEY[:20]}..." if SANTIMENT_API_KEY else "NO API KEY")

# Simple query for Bitcoin
slug = "bitcoin"
# Free tier only allows data older than 30 days
end_date = datetime.utcnow() - timedelta(days=31)
start_date = end_date - timedelta(days=7)

from_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
to_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

query = """
{
  getMetric(metric: "social_volume_total") {
    timeseriesData(
      slug: "%s"
      from: "%s"
      to: "%s"
      interval: "1d"
    ) {
      datetime
      value
    }
  }
}
""" % (slug, from_str, to_str)

print(f"\nQuerying Santiment for {slug} from {from_str} to {to_str}")

try:
    response = requests.post(
        "https://api.santiment.net/graphql",
        json={"query": query},
        headers={
            "Authorization": f"Apikey {SANTIMENT_API_KEY}",
            "Content-Type": "application/json"
        },
        timeout=10
    )
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"\nResponse Headers: {dict(response.headers)}")
    print(f"\nResponse Body:")
    print(response.text)
    
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print("\n❌ GraphQL Errors:")
            for error in data['errors']:
                print(f"  - {error}")
        elif 'data' in data:
            print("\n✅ Success! Data received:")
            timeseries = data.get('data', {}).get('getMetric', {}).get('timeseriesData', [])
            print(f"  Found {len(timeseries)} data points")
            if timeseries:
                print(f"  Latest: {timeseries[-1]}")
    else:
        print(f"\n❌ API Error: {response.status_code}")
        
except Exception as e:
    print(f"\n❌ Exception: {type(e).__name__}: {e}")
