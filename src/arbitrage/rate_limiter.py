"""
Rate Limiting Middleware
Implements token bucket algorithm for API rate limiting
"""
from __future__ import annotations
import time
import sqlite3
from typing import Optional
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'var', 'users.db')

# Rate limit configuration
RATE_LIMITS = {
    # Endpoint pattern: (requests_per_window, window_seconds)
    'default': (100, 60),  # 100 requests per minute
    'auth': (5, 60),  # 5 login attempts per minute
    'trading': (30, 60),  # 30 trades per minute
    'websocket': (10, 60),  # 10 WebSocket connections per minute
    'public': (200, 60),  # 200 requests per minute for public endpoints
}


def get_rate_limit_key(endpoint: str) -> tuple:
    """Determine rate limit category for endpoint"""
    if '/auth/' in endpoint or '/login' in endpoint or '/register' in endpoint:
        return RATE_LIMITS['auth']
    elif '/manual-trade' in endpoint or '/live-strategy' in endpoint:
        return RATE_LIMITS['trading']
    elif '/ws/' in endpoint:
        return RATE_LIMITS['websocket']
    elif '/api/opportunities' in endpoint or '/api/hotcoins' in endpoint:
        return RATE_LIMITS['public']
    else:
        return RATE_LIMITS['default']


def check_rate_limit(user_id: Optional[int], ip_address: str, endpoint: str) -> bool:
    """
    Check if request is within rate limits
    Returns: True if allowed, raises HTTPException if rate limit exceeded
    """
    requests_allowed, window_seconds = get_rate_limit_key(endpoint)
    
    # Use user_id if authenticated, otherwise use IP address
    identifier = str(user_id) if user_id else ip_address
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get current window data
        cursor.execute("""
            SELECT request_count, window_start
            FROM rate_limits
            WHERE (user_id = ? OR ip_address = ?) AND endpoint = ?
        """, (user_id, ip_address, endpoint))
        
        row = cursor.fetchone()
        current_time = datetime.utcnow()
        
        if row:
            request_count, window_start_str = row
            window_start = datetime.fromisoformat(window_start_str)
            
            # Check if window has expired
            if current_time - window_start > timedelta(seconds=window_seconds):
                # Reset window
                cursor.execute("""
                    UPDATE rate_limits
                    SET request_count = 1, window_start = ?
                    WHERE (user_id = ? OR ip_address = ?) AND endpoint = ?
                """, (current_time.isoformat(), user_id, ip_address, endpoint))
                conn.commit()
                return True
            
            # Check if limit exceeded
            if request_count >= requests_allowed:
                retry_after = int((window_start + timedelta(seconds=window_seconds) - current_time).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Increment counter
            cursor.execute("""
                UPDATE rate_limits
                SET request_count = request_count + 1
                WHERE (user_id = ? OR ip_address = ?) AND endpoint = ?
            """, (user_id, ip_address, endpoint))
            conn.commit()
            return True
        
        else:
            # First request - create new window
            cursor.execute("""
                INSERT INTO rate_limits (user_id, ip_address, endpoint, request_count, window_start)
                VALUES (?, ?, ?, 1, ?)
            """, (user_id, ip_address, endpoint, current_time.isoformat()))
            conn.commit()
            return True
            
    finally:
        conn.close()


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware to enforce rate limits on all requests
    """
    # Skip rate limiting for health checks
    if request.url.path in ['/health', '/']:
        return await call_next(request)
    
    # Get client IP
    ip_address = request.client.host if request.client else "unknown"
    
    # Get user_id from request state (set by auth middleware)
    user_id = getattr(request.state, 'user_id', None)
    
    # Check rate limit
    try:
        check_rate_limit(user_id, ip_address, request.url.path)
    except HTTPException as e:
        # Log rate limit violations
        print(f"[RATE LIMIT] Blocked {ip_address} (user: {user_id}) on {request.url.path}: {e.detail}")
        raise e
    
    response = await call_next(request)
    return response


def cleanup_old_rate_limits():
    """
    Cleanup rate limit records older than 24 hours
    Should be run periodically (e.g., daily cron job)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cutoff_time = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        cursor.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff_time,))
        deleted = cursor.rowcount
        conn.commit()
        
        if deleted > 0:
            print(f"[RATE LIMIT] Cleaned up {deleted} old rate limit records")
        
        return deleted
        
    finally:
        conn.close()


import os  # Add this import at the top
