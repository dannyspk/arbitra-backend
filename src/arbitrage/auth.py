"""
Authentication and Authorization System
Implements JWT-based authentication with secure password hashing
"""
from __future__ import annotations
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import sqlite3
import hashlib
import hmac

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from passlib.context import CryptContext

# JWT Configuration
SECRET_KEY = os.getenv('JWT_SECRET_KEY', secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'var', 'users.db')


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class User(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool = True
    created_at: str


def init_db():
    """Initialize users database"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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
            is_admin BOOLEAN DEFAULT 0,
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
            encrypted_api_key TEXT NOT NULL,
            encrypted_secret TEXT NOT NULL,
            encrypted_passphrase TEXT,
            is_testnet BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, exchange, is_testnet)
        )
    """)
    
    # Session tokens table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Rate limiting table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ip_address TEXT,
            endpoint TEXT NOT NULL,
            request_count INTEGER DEFAULT 1,
            window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ip_address, endpoint)
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"[AUTH] Database initialized at {DB_PATH}")


# Password utilities
def hash_password(password: str) -> str:
    """Hash a password for storing"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a stored password against one provided by user"""
    return pwd_context.verify(plain_password, hashed_password)


# JWT utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: int) -> str:
    """Create refresh token and store in database"""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token_data = {
        "user_id": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)  # Unique token ID
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expire)
    )
    conn.commit()
    conn.close()
    
    return token


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# User CRUD operations
def create_user(username: str, email: str, password: str) -> User:
    """Create a new user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        hashed_password = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, email, hashed_password) VALUES (?, ?, ?)",
            (username, email, hashed_password)
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        
        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            is_active=bool(row[4]),
            created_at=row[6]
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user and return user object"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    if not verify_password(password, row[3]):
        return None
    
    # Update last login
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    
    return User(
        id=row[0],
        username=row[1],
        email=row[2],
        is_active=bool(row[4]),
        created_at=row[6]
    )


def get_user_by_id(user_id: int) -> Optional[User]:
    """Get user by ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return User(
        id=row[0],
        username=row[1],
        email=row[2],
        is_active=bool(row[4]),
        created_at=row[6]
    )


# Dependency to get current user from token
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Dependency to extract and validate current user from JWT token"""
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Optional authentication - returns None if no token provided"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = decode_token(token)
        user_id = payload.get("user_id")
        if user_id:
            return get_user_by_id(user_id)
    except:
        pass
    
    return None


# WebSocket authentication
async def authenticate_websocket(websocket) -> Optional[User]:
    """Authenticate WebSocket connection using token from query params or headers"""
    # Try to get token from query parameters
    token = websocket.query_params.get("token")
    
    if not token:
        # Try to get from headers
        token = websocket.headers.get("authorization")
        if token and token.startswith("Bearer "):
            token = token.replace("Bearer ", "")
    
    if not token:
        return None
    
    try:
        payload = decode_token(token)
        user_id = payload.get("user_id")
        if user_id:
            user = get_user_by_id(user_id)
            if user and user.is_active:
                return user
    except:
        pass
    
    return None


# Initialize database on module import
init_db()
