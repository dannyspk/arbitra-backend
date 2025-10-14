"""
Authentication API Endpoints
Handles user registration, login, token refresh, and API key management
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from .auth import (
    User, UserCreate, UserLogin, Token,
    create_user, authenticate_user, create_access_token,
    create_refresh_token, decode_token, get_current_user,
    get_user_by_id
)
from .encryption import (
    save_api_keys, get_api_keys, list_user_exchanges,
    delete_api_keys, EncryptedAPIKey
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class APIKeyRequest(BaseModel):
    exchange: str
    api_key: str
    secret: str
    passphrase: Optional[str] = None
    is_testnet: bool = False


class APIKeyResponse(BaseModel):
    id: int
    exchange: str
    is_testnet: bool
    created_at: str


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user account
    """
    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    user = create_user(request.username, request.email, request.password)
    return user


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    Login and receive access + refresh tokens
    """
    user = authenticate_user(request.username, request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens
    access_token = create_access_token({"user_id": user.id, "username": user.username})
    refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=Token)
async def refresh(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    """
    try:
        payload = decode_token(request.refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("user_id")
        user = get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Create new access token
        access_token = create_access_token({"user_id": user.id, "username": user.username})
        
        return Token(
            access_token=access_token,
            refresh_token=request.refresh_token  # Return same refresh token
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information
    """
    return current_user


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def add_api_keys(
    request: APIKeyRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Add or update encrypted API keys for an exchange
    """
    key_id = save_api_keys(
        user_id=current_user.id,
        exchange=request.exchange,
        api_key=request.api_key,
        secret=request.secret,
        passphrase=request.passphrase,
        is_testnet=request.is_testnet
    )
    
    return {
        "success": True,
        "message": f"API keys saved for {request.exchange}",
        "key_id": key_id
    }


@router.get("/api-keys", response_model=list[EncryptedAPIKey])
async def list_api_keys(current_user: User = Depends(get_current_user)):
    """
    List all configured exchanges (without exposing actual keys)
    """
    return list_user_exchanges(current_user.id)


@router.delete("/api-keys/{exchange}")
async def remove_api_keys(
    exchange: str,
    is_testnet: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Delete API keys for an exchange
    """
    deleted = delete_api_keys(current_user.id, exchange, is_testnet)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API keys found for {exchange}"
        )
    
    return {
        "success": True,
        "message": f"API keys deleted for {exchange}"
    }


@router.get("/api-keys/{exchange}/test")
async def test_api_keys(
    exchange: str,
    is_testnet: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Test if API keys work by fetching balance
    """
    keys = get_api_keys(current_user.id, exchange, is_testnet)
    
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API keys found for {exchange}"
        )
    
    try:
        import ccxt
        
        # Create exchange instance
        exchange_class = getattr(ccxt, exchange.lower())
        exchange_instance = exchange_class({
            'apiKey': keys['api_key'],
            'secret': keys['secret'],
            'password': keys.get('passphrase'),
            'enableRateLimit': True,
        })
        
        if is_testnet:
            exchange_instance.set_sandbox_mode(True)
        
        # Test by fetching balance
        balance = exchange_instance.fetch_balance()
        
        return {
            "success": True,
            "message": f"API keys are valid for {exchange}",
            "total_balance_usd": balance.get('total', {}).get('USD', 'N/A')
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"API keys test failed: {str(e)}"
        }
