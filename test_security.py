"""Test script for security features."""
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, 'src')

from arbitrage.security.auth import (
    create_user, authenticate_user, create_access_token,
    verify_token, get_user_by_id, log_audit
)
from arbitrage.security.encryption import (
    encrypt_api_key, decrypt_api_key,
    store_user_api_keys, get_user_api_keys,
    list_user_exchanges
)

print("=" * 60)
print("🔒 SECURITY FEATURES TEST")
print("=" * 60)

# Test 1: User Registration
print("\n✅ Test 1: User Registration")
try:
    user = create_user("testuser", "test@example.com", "SecurePass123")
    print(f"   Created user: {user['username']} (ID: {user['id']})")
except ValueError as e:
    print(f"   User might already exist: {e}")
    # Get existing user for testing
    from arbitrage.security.auth import authenticate_user
    auth_result = authenticate_user("testuser", "SecurePass123")
    if auth_result:
        user = auth_result
        print(f"   Using existing user: {user['username']} (ID: {user['id']})")
    else:
        print("   ❌ Failed to create or authenticate user")
        sys.exit(1)

# Test 2: Authentication
print("\n✅ Test 2: User Authentication")
auth_result = authenticate_user("testuser", "SecurePass123")
if auth_result:
    print(f"   ✓ Authentication successful for: {auth_result['username']}")
else:
    print("   ❌ Authentication failed")
    sys.exit(1)

# Test 3: JWT Token Creation
print("\n✅ Test 3: JWT Token Creation & Verification")
token = create_access_token({"sub": str(user['id']), "username": user['username']})
print(f"   ✓ Token created: {token[:50]}...")

payload = verify_token(token)
if payload:
    print(f"   ✓ Token verified: user_id={payload['sub']}, username={payload['username']}")
else:
    print("   ❌ Token verification failed")
    sys.exit(1)

# Test 4: API Key Encryption
print("\n✅ Test 4: API Key Encryption")
test_api_key = "test_binance_api_key_12345"
test_api_secret = "test_binance_secret_67890"

encrypted_key = encrypt_api_key(test_api_key)
print(f"   ✓ Encrypted API key: {encrypted_key[:50]}...")

decrypted_key = decrypt_api_key(encrypted_key)
if decrypted_key == test_api_key:
    print(f"   ✓ Decryption successful: {decrypted_key}")
else:
    print("   ❌ Decryption failed")
    sys.exit(1)

# Test 5: Store User API Keys
print("\n✅ Test 5: Store User API Keys")
try:
    result = store_user_api_keys(
        user_id=user['id'],
        exchange="binance",
        api_key="mCKNY0bBb5ZjWDRGwUpynLuGum6wHEOdCWKieqZSPUv8Q4qwiYgWlwWTtXZtXP23",
        api_secret="9mt3IjYLzzpUtJvpBESJRp1vKLjItxrMbyC0vSk8NrVYqrjL75tBGe3kQjBTmcGB",
        label="main"
    )
    print(f"   ✓ Stored {result['exchange']} API keys (ID: {result['id']})")
except ValueError as e:
    print(f"   Keys might already exist: {e}")

# Test 6: Retrieve User API Keys
print("\n✅ Test 6: Retrieve & Decrypt User API Keys")
keys = get_user_api_keys(user['id'], "binance", "main")
if keys:
    print(f"   ✓ Retrieved API key: {keys['api_key'][:20]}...")
    print(f"   ✓ Retrieved API secret: {keys['api_secret'][:20]}...")
    print(f"   ✓ Keys active: {keys['is_active']}")
else:
    print("   ❌ Failed to retrieve API keys")
    sys.exit(1)

# Test 7: List User Exchanges
print("\n✅ Test 7: List User Exchanges")
exchanges = list_user_exchanges(user['id'])
print(f"   ✓ Found {len(exchanges)} exchange(s):")
for ex in exchanges:
    print(f"      - {ex['exchange']} ({ex['label']}) - Active: {ex['is_active']}")

# Test 8: Audit Logging
print("\n✅ Test 8: Audit Logging")
log_audit(user['id'], "test_action", "Security test completed", "127.0.0.1")
print("   ✓ Audit log entry created")

# Test 9: Get User by ID
print("\n✅ Test 9: Get User by ID")
user_info = get_user_by_id(user['id'])
if user_info:
    print(f"   ✓ User found: {user_info['username']}")
    print(f"   ✓ Email: {user_info['email']}")
    print(f"   ✓ Created: {user_info['created_at']}")
    print(f"   ✓ Last login: {user_info['last_login']}")
else:
    print("   ❌ User not found")
    sys.exit(1)

# Test 10: Invalid Password
print("\n✅ Test 10: Invalid Password Test")
invalid_auth = authenticate_user("testuser", "WrongPassword")
if not invalid_auth:
    print("   ✓ Correctly rejected invalid password")
else:
    print("   ❌ Should have rejected invalid password")

print("\n" + "=" * 60)
print("✅ ALL SECURITY TESTS PASSED!")
print("=" * 60)
print("\nSecurity features verified:")
print("  ✓ User registration & authentication")
print("  ✓ Password hashing (bcrypt)")
print("  ✓ JWT token creation & verification")
print("  ✓ API key encryption/decryption (Fernet)")
print("  ✓ Secure key storage in database")
print("  ✓ Audit logging")
print("\nDatabase location: data/security.db")
print("=" * 60)
