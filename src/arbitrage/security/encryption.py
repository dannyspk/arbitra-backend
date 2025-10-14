"""API key encryption for secure storage of user exchange credentials."""
import os
from cryptography.fernet import Fernet
import sqlite3
from typing import Optional, List

# Load encryption key from environment
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY not set in environment variables")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

DB_PATH = "data/security.db"


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key."""
    return cipher_suite.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key."""
    return cipher_suite.decrypt(encrypted_key.encode()).decode()


def store_user_api_keys(
    user_id: int,
    exchange: str,
    api_key: str,
    api_secret: str,
    label: str = "default"
) -> dict:
    """Store encrypted API keys for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    encrypted_key = encrypt_api_key(api_key)
    encrypted_secret = encrypt_api_key(api_secret)
    
    try:
        cursor.execute("""
            INSERT INTO user_api_keys (user_id, exchange, api_key_encrypted, api_secret_encrypted, label)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, exchange, encrypted_key, encrypted_secret, label))
        conn.commit()
        key_id = cursor.lastrowid
        
        # Log the action
        from .auth import log_audit
        log_audit(user_id, "api_key_added", f"Added {exchange} API keys with label '{label}'")
        
        return {"id": key_id, "exchange": exchange, "label": label, "status": "active"}
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"API keys for {exchange} with label '{label}' already exist")
    finally:
        conn.close()


def get_user_api_keys(user_id: int, exchange: str, label: str = "default") -> Optional[dict]:
    """Retrieve and decrypt API keys for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT api_key_encrypted, api_secret_encrypted, is_active
        FROM user_api_keys
        WHERE user_id = ? AND exchange = ? AND label = ? AND is_active = 1
    """, (user_id, exchange, label))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return None
    
    encrypted_key, encrypted_secret, is_active = result
    
    return {
        "api_key": decrypt_api_key(encrypted_key),
        "api_secret": decrypt_api_key(encrypted_secret),
        "is_active": is_active
    }


def list_user_exchanges(user_id: int) -> List[dict]:
    """List all exchanges configured for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, exchange, label, is_active, created_at
        FROM user_api_keys
        WHERE user_id = ?
    """, (user_id,))
    
    exchanges = []
    for row in cursor.fetchall():
        exchanges.append({
            "id": row[0],
            "exchange": row[1],
            "label": row[2],
            "is_active": row[3],
            "created_at": row[4]
        })
    
    conn.close()
    return exchanges


def delete_user_api_keys(user_id: int, key_id: int) -> bool:
    """Delete (deactivate) user API keys."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE user_api_keys
        SET is_active = 0
        WHERE id = ? AND user_id = ?
    """, (key_id, user_id))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected > 0:
        from .auth import log_audit
        log_audit(user_id, "api_key_deleted", f"Deleted API key ID {key_id}")
    
    return affected > 0


def update_user_api_keys(
    user_id: int,
    key_id: int,
    api_key: str = None,
    api_secret: str = None
) -> bool:
    """Update user API keys."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if api_key:
        updates.append("api_key_encrypted = ?")
        params.append(encrypt_api_key(api_key))
    
    if api_secret:
        updates.append("api_secret_encrypted = ?")
        params.append(encrypt_api_key(api_secret))
    
    if not updates:
        conn.close()
        return False
    
    query = f"UPDATE user_api_keys SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
    params.extend([key_id, user_id])
    
    cursor.execute(query, params)
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected > 0:
        from .auth import log_audit
        log_audit(user_id, "api_key_updated", f"Updated API key ID {key_id}")
    
    return affected > 0
