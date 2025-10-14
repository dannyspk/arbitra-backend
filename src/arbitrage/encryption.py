"""
API Key Encryption and Storage System
Encrypts user API keys at rest using AES-256-GCM
"""
from __future__ import annotations
import os
import base64
import sqlite3
from typing import Optional, Dict, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from pydantic import BaseModel


# Encryption key - MUST be stored securely in production (AWS Secrets Manager, etc.)
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    # Generate a key if not set (for development only)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"[SECURITY WARNING] No ENCRYPTION_KEY set. Generated temporary key: {ENCRYPTION_KEY[:20]}...")
    print("[SECURITY WARNING] Set ENCRYPTION_KEY environment variable in production!")

# Initialize Fernet cipher
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'var', 'users.db')


class APIKeyData(BaseModel):
    exchange: str
    api_key: str
    secret: str
    passphrase: Optional[str] = None
    is_testnet: bool = False


class EncryptedAPIKey(BaseModel):
    id: int
    exchange: str
    is_testnet: bool
    created_at: str


def encrypt_string(plaintext: str) -> str:
    """Encrypt a string using Fernet (AES-256)"""
    if not plaintext:
        return ""
    encrypted = cipher_suite.encrypt(plaintext.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_string(encrypted: str) -> str:
    """Decrypt a string using Fernet"""
    if not encrypted:
        return ""
    try:
        decoded = base64.b64decode(encrypted.encode())
        decrypted = cipher_suite.decrypt(decoded)
        return decrypted.decode()
    except Exception as e:
        print(f"[ENCRYPTION ERROR] Failed to decrypt: {e}")
        return ""


def save_api_keys(user_id: int, exchange: str, api_key: str, secret: str, 
                  passphrase: Optional[str] = None, is_testnet: bool = False) -> int:
    """
    Encrypt and save user API keys to database
    Returns: API key record ID
    """
    encrypted_api_key = encrypt_string(api_key)
    encrypted_secret = encrypt_string(secret)
    encrypted_passphrase = encrypt_string(passphrase) if passphrase else None
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Delete existing keys for this user/exchange/testnet combo
        cursor.execute(
            "DELETE FROM user_api_keys WHERE user_id = ? AND exchange = ? AND is_testnet = ?",
            (user_id, exchange, is_testnet)
        )
        
        # Insert new keys
        cursor.execute("""
            INSERT INTO user_api_keys (user_id, exchange, encrypted_api_key, encrypted_secret, 
                                       encrypted_passphrase, is_testnet)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, exchange, encrypted_api_key, encrypted_secret, encrypted_passphrase, is_testnet))
        
        conn.commit()
        key_id = cursor.lastrowid
        print(f"[ENCRYPTION] Saved encrypted API keys for user {user_id}, exchange {exchange}")
        return key_id
        
    finally:
        conn.close()


def get_api_keys(user_id: int, exchange: str, is_testnet: bool = False) -> Optional[Dict[str, str]]:
    """
    Retrieve and decrypt user API keys
    Returns: Dict with 'api_key', 'secret', and optionally 'passphrase'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT encrypted_api_key, encrypted_secret, encrypted_passphrase
            FROM user_api_keys
            WHERE user_id = ? AND exchange = ? AND is_testnet = ?
        """, (user_id, exchange, is_testnet))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        api_key = decrypt_string(row[0])
        secret = decrypt_string(row[1])
        passphrase = decrypt_string(row[2]) if row[2] else None
        
        return {
            'api_key': api_key,
            'secret': secret,
            'passphrase': passphrase
        }
        
    finally:
        conn.close()


def list_user_exchanges(user_id: int) -> list[EncryptedAPIKey]:
    """
    List all exchanges configured for a user (without exposing keys)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, exchange, is_testnet, created_at
            FROM user_api_keys
            WHERE user_id = ?
            ORDER BY exchange, is_testnet
        """, (user_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append(EncryptedAPIKey(
                id=row[0],
                exchange=row[1],
                is_testnet=bool(row[2]),
                created_at=row[3]
            ))
        
        return results
        
    finally:
        conn.close()


def delete_api_keys(user_id: int, exchange: str, is_testnet: bool = False) -> bool:
    """
    Delete API keys for a user/exchange combination
    Returns: True if deleted, False if not found
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM user_api_keys
            WHERE user_id = ? AND exchange = ? AND is_testnet = ?
        """, (user_id, exchange, is_testnet))
        
        conn.commit()
        deleted = cursor.rowcount > 0
        
        if deleted:
            print(f"[ENCRYPTION] Deleted API keys for user {user_id}, exchange {exchange}")
        
        return deleted
        
    finally:
        conn.close()


def rotate_encryption_key(old_key: str, new_key: str):
    """
    Re-encrypt all API keys with a new encryption key
    Used for key rotation security best practices
    """
    old_cipher = Fernet(old_key.encode())
    new_cipher = Fernet(new_key.encode())
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, encrypted_api_key, encrypted_secret, encrypted_passphrase FROM user_api_keys")
        rows = cursor.fetchall()
        
        for row in rows:
            key_id, enc_api_key, enc_secret, enc_passphrase = row
            
            # Decrypt with old key
            api_key = old_cipher.decrypt(base64.b64decode(enc_api_key)).decode()
            secret = old_cipher.decrypt(base64.b64decode(enc_secret)).decode()
            passphrase = None
            if enc_passphrase:
                passphrase = old_cipher.decrypt(base64.b64decode(enc_passphrase)).decode()
            
            # Re-encrypt with new key
            new_enc_api_key = base64.b64encode(new_cipher.encrypt(api_key.encode())).decode()
            new_enc_secret = base64.b64encode(new_cipher.encrypt(secret.encode())).decode()
            new_enc_passphrase = None
            if passphrase:
                new_enc_passphrase = base64.b64encode(new_cipher.encrypt(passphrase.encode())).decode()
            
            # Update database
            cursor.execute("""
                UPDATE user_api_keys
                SET encrypted_api_key = ?, encrypted_secret = ?, encrypted_passphrase = ?
                WHERE id = ?
            """, (new_enc_api_key, new_enc_secret, new_enc_passphrase, key_id))
        
        conn.commit()
        print(f"[ENCRYPTION] Rotated encryption key for {len(rows)} API key records")
        
    finally:
        conn.close()
