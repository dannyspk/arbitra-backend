"""Authentication and user management."""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt

# Password hashing - configure bcrypt properly
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

DB_PATH = "data/security.db"


def init_security_db():
    """Initialize security database with users and API keys tables."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    
    # User API keys table (encrypted)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exchange TEXT NOT NULL,
            api_key_encrypted TEXT NOT NULL,
            api_secret_encrypted TEXT NOT NULL,
            label TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, exchange, label)
        )
    """)
    
    # Sessions table for tracking active sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # Audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Security database initialized at {DB_PATH}")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_user(username: str, email: str, password: str) -> dict:
    """Create a new user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    hashed_password = get_password_hash(password)
    
    try:
        cursor.execute("""
            INSERT INTO users (username, email, hashed_password)
            VALUES (?, ?, ?)
        """, (username, email, hashed_password))
        conn.commit()
        user_id = cursor.lastrowid
        
        # Log the action
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, 'user_created', ?)
        """, (user_id, f"User {username} registered"))
        conn.commit()
        
        return {"id": user_id, "username": username, "email": email}
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"User creation failed: {str(e)}")
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user by username and password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, username, email, hashed_password, is_active
        FROM users WHERE username = ?
    """, (username,))
    
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return None
    
    user_id, username, email, hashed_password, is_active = user
    
    if not is_active:
        conn.close()
        return None
    
    if not verify_password(password, hashed_password):
        conn.close()
        return None
    
    # Update last login
    cursor.execute("""
        UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
    """, (user_id,))
    conn.commit()
    
    # Log successful login
    cursor.execute("""
        INSERT INTO audit_log (user_id, action)
        VALUES (?, 'login_success')
    """, (user_id,))
    conn.commit()
    
    conn.close()
    
    return {"id": user_id, "username": username, "email": email}


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, username, email, is_active, created_at, last_login
        FROM users WHERE id = ?
    """, (user_id,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return None
    
    return {
        "id": user[0],
        "username": user[1],
        "email": user[2],
        "is_active": user[3],
        "created_at": user[4],
        "last_login": user[5]
    }


def log_audit(user_id: Optional[int], action: str, details: str = None, ip_address: str = None):
    """Log an audit event."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO audit_log (user_id, action, details, ip_address)
        VALUES (?, ?, ?, ?)
    """, (user_id, action, details, ip_address))
    
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Initialize database when run directly
    init_security_db()
