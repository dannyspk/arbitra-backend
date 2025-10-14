"""Quick debug script to test API endpoints."""
import requests

BASE_URL = "http://localhost:8000"

# Test 1: Login to get a valid token
print("🔐 Test 1: Login")
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    json={"username": "testuser_10049", "password": "TestPassword123!"}
)
print(f"Status: {login_response.status_code}")
if login_response.status_code == 200:
    data = login_response.json()
    token = data['access_token']
    print(f"✓ Got token: {token[:50]}...")
    
    # Test 2: Get current user info
    print("\n👤 Test 2: Get Current User Info")
    me_response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {me_response.status_code}")
    print(f"Response: {me_response.text}")
    
    # Test 3: Add API keys
    print("\n🔑 Test 3: Add Encrypted API Keys")
    keys_response = requests.post(
        f"{BASE_URL}/api/user/api-keys",
        json={
            "exchange": "binance",
            "api_key": "test_key_123",
            "api_secret": "test_secret_456",
            "label": "My Binance Account"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {keys_response.status_code}")
    print(f"Response: {keys_response.text}")
    
    # Test 4: List exchanges
    print("\n📋 Test 4: List Configured Exchanges")
    list_response = requests.get(
        f"{BASE_URL}/api/user/api-keys",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {list_response.status_code}")
    print(f"Response: {list_response.text}")
    
    # Test 5: Protected endpoint (manual trade)
    print("\n💰 Test 5: Protected Endpoint (Manual Trade)")
    trade_response = requests.post(
        f"{BASE_URL}/api/manual-trade",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "amount": 0.001
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {trade_response.status_code}")
    print(f"Response: {trade_response.text[:200]}...")
else:
    print(f"❌ Login failed: {login_response.text}")
