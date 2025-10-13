#!/usr/bin/env python3
"""
Check Railway's Public IP and API Key Configuration
Run this to verify what IP Railway is using and if API keys are set correctly
"""

import requests
import sys

RAILWAY_URL = "https://arbitra-backend-production.up.railway.app"

def check_ip():
    """Check Railway's outbound IP address"""
    print("\n" + "="*60)
    print("🌐 CHECKING RAILWAY PUBLIC IP")
    print("="*60 + "\n")
    
    try:
        # Call a simple endpoint that will show Railway's IP
        response = requests.get(f"{RAILWAY_URL}/api/debug/ip", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Railway Backend is Online!")
            print(f"\n📍 Railway's Public IP: {data.get('ip', 'Unknown')}")
            print(f"🌍 Location: {data.get('country', 'Unknown')}")
            print(f"🏢 ISP: {data.get('org', 'Unknown')}")
            
            print("\n" + "="*60)
            print("📋 NEXT STEPS:")
            print("="*60)
            print(f"\n1. Add this IP to Binance API whitelist: {data.get('ip', 'Unknown')}")
            print("2. Go to: https://www.binance.com/en/my/settings/api-management")
            print("3. Edit your API key")
            print("4. Add the IP above to the whitelist")
            print("5. Enable 'Enable Futures' permission")
            print("6. Save changes")
            print("\n⚠️  Note: Railway IPs can change on redeployment!")
            
            return data.get('ip')
        else:
            print(f"❌ Error: Backend returned status code {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Cannot reach Railway backend")
        print(f"URL: {RAILWAY_URL}")
        print("\nPossible issues:")
        print("  - Railway service is down")
        print("  - Network connectivity issues")
        print("  - URL is incorrect")
        
    except requests.exceptions.Timeout:
        print("❌ Timeout: Railway backend didn't respond in time")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print(f"Type: {type(e).__name__}")
    
    return None

def check_api_keys():
    """Check if API keys are configured on Railway"""
    print("\n" + "="*60)
    print("🔑 CHECKING API KEY CONFIGURATION")
    print("="*60 + "\n")
    
    try:
        response = requests.get(f"{RAILWAY_URL}/api/debug/config", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"API Key Set: {'✅' if data.get('has_api_key') else '❌'}")
            print(f"API Secret Set: {'✅' if data.get('has_api_secret') else '❌'}")
            print(f"Live Orders Enabled: {'✅' if data.get('live_orders_enabled') else '❌'}")
            
            if data.get('has_api_key'):
                print(f"\nAPI Key (first 10 chars): {data.get('api_key_preview', 'N/A')}")
            
            if data.get('has_api_secret'):
                print(f"API Secret (first 10 chars): {data.get('api_secret_preview', 'N/A')}")
            
            print(f"\nEnvironment Variables:")
            print(f"  ARB_ALLOW_LIVE_ORDERS: {data.get('live_orders_flag', 'Not Set')}")
            
            if not data.get('has_api_key') or not data.get('has_api_secret'):
                print("\n⚠️  WARNING: API credentials not configured on Railway!")
                print("\nTo fix:")
                print("1. Go to Railway dashboard")
                print("2. Select your project")
                print("3. Go to Variables tab")
                print("4. Add BINANCE_API_KEY and BINANCE_API_SECRET")
                
        else:
            print(f"❌ Error: Backend returned status code {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error checking configuration: {e}")

def test_binance_connection():
    """Test if Railway can connect to Binance with the configured API keys"""
    print("\n" + "="*60)
    print("🔌 TESTING BINANCE CONNECTION")
    print("="*60 + "\n")
    
    try:
        response = requests.get(f"{RAILWAY_URL}/api/debug/test-binance", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success'):
                print("✅ Successfully connected to Binance!")
                print(f"\n📊 Account Info:")
                print(f"  Can Trade: {'✅' if data.get('can_trade') else '❌'}")
                print(f"  Futures Enabled: {'✅' if data.get('futures_enabled') else '❌'}")
                
                if data.get('balances'):
                    print(f"\n💰 Sample Balances:")
                    for bal in data.get('balances', [])[:5]:
                        print(f"  {bal}")
            else:
                print("❌ Failed to connect to Binance")
                print(f"\nError: {data.get('error', 'Unknown error')}")
                
                if 'Invalid Api-Key ID' in str(data.get('error', '')):
                    print("\n🔍 This means:")
                    print("  - API key is incorrect or doesn't exist")
                    print("  - Double-check the API key in Railway variables")
                    print("  - Make sure there are no extra spaces or characters")
                    
                elif 'IP' in str(data.get('error', '')):
                    print("\n🔍 This means:")
                    print("  - Railway's IP is not whitelisted on Binance")
                    print("  - Add the IP shown above to your Binance API whitelist")
                    
        else:
            print(f"❌ Error: Backend returned status code {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing Binance connection: {e}")

if __name__ == "__main__":
    print("\n" + "🚂 " * 20)
    print("RAILWAY DEPLOYMENT CHECKER")
    print("🚂 " * 20)
    
    # Check IP
    ip = check_ip()
    
    # Check API keys
    check_api_keys()
    
    # Test Binance connection
    test_binance_connection()
    
    print("\n" + "="*60)
    print("✅ Check Complete!")
    print("="*60 + "\n")
