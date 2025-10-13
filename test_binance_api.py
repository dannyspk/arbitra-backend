"""
Test Binance API Connection
Run this to verify your API keys are configured correctly
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("\n" + "=" * 60)
print("🔍 BINANCE API CONNECTION TEST")
print("=" * 60 + "\n")

# Check if API keys are set
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

if not api_key:
    print("❌ BINANCE_API_KEY not found in environment")
    print("   Add it to your .env file")
    sys.exit(1)

if not api_secret:
    print("❌ BINANCE_API_SECRET not found in environment")
    print("   Add it to your .env file")
    sys.exit(1)

print("✅ API credentials found in environment\n")

# Test connection
try:
    import ccxt
    
    print("Step 1: Creating Binance exchange object...")
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    print("✅ Exchange object created\n")
    
    print("Step 2: Fetching account balance...")
    balance = exchange.fetch_balance()
    print("✅ Successfully connected to Binance!\n")
    
    # Display balance
    print("Account Balance:")
    print("-" * 40)
    
    total_usdt = 0
    for currency, amount in balance['total'].items():
        if amount > 0:
            try:
                # Try to get USDT value
                if currency == 'USDT':
                    usdt_value = amount
                else:
                    ticker = exchange.fetch_ticker(f'{currency}/USDT')
                    usdt_value = amount * ticker['last']
                
                if usdt_value > 0.01:  # Only show significant amounts
                    total_usdt += usdt_value
                    print(f"{currency:8} {amount:12.8f} (~${usdt_value:.2f})")
            except:
                if amount > 0.0001:
                    print(f"{currency:8} {amount:12.8f}")
    
    print("-" * 40)
    print(f"Total Value: ~${total_usdt:.2f} USDT\n")
    
    # Check permissions
    print("Step 3: Checking API permissions...")
    try:
        # Try to fetch open orders (requires spot trading permission)
        orders = exchange.fetch_open_orders(limit=1)
        print("✅ Spot trading permission: OK")
    except Exception as e:
        print(f"⚠️  Spot trading permission: {str(e)}")
    
    try:
        # Try to fetch positions (requires futures permission)
        exchange.options['defaultType'] = 'future'
        positions = exchange.fetch_positions()
        print("✅ Futures trading permission: OK")
    except Exception as e:
        print(f"⚠️  Futures trading permission: {str(e)}")
    
    print("\n" + "=" * 60)
    print("✅ API CONNECTION TEST PASSED!")
    print("=" * 60)
    print("\nYou can now enable live trading by setting:")
    print("ARB_ALLOW_LIVE_EXECUTION=1")
    print("\n🚨 Remember: Start with small positions and test thoroughly!")
    print()
    
except ImportError:
    print("❌ ccxt library not found")
    print("   Install it with: pip install ccxt")
    sys.exit(1)
    
except ccxt.AuthenticationError as e:
    print(f"\n❌ AUTHENTICATION ERROR:")
    print(f"   {str(e)}")
    print("\nPossible issues:")
    print("   - API key is incorrect")
    print("   - API secret is incorrect")  
    print("   - API key permissions are insufficient")
    print("   - IP whitelist restriction (if enabled)")
    sys.exit(1)
    
except ccxt.NetworkError as e:
    print(f"\n❌ NETWORK ERROR:")
    print(f"   {str(e)}")
    print("\nPossible issues:")
    print("   - No internet connection")
    print("   - Binance API is down")
    print("   - Firewall blocking connection")
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ UNEXPECTED ERROR:")
    print(f"   {str(e)}")
    print(f"   Type: {type(e).__name__}")
    sys.exit(1)
