"""Rate limiting middleware for API protection."""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute", "2000/hour", "10000/day"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# Rate limit configurations for different endpoint types
RATE_LIMITS = {
    # Authentication endpoints - stricter limits to prevent brute force
    "auth": "10/minute",
    
    # Trading endpoints - moderate limits
    "trading": "30/minute",
    
    # Data retrieval endpoints - more permissive
    "data": "100/minute",
    
    # WebSocket connections - very strict
    "websocket": "5/minute",
    
    # Public endpoints - permissive
    "public": "200/minute",
}


def get_rate_limit(endpoint_type: str) -> str:
    """Get rate limit configuration for endpoint type."""
    return RATE_LIMITS.get(endpoint_type, "100/minute")
