"""
Security Integration Instructions for web.py

This file contains the code snippets to add to web.py for full security implementation.
"""

# =============================================================================
# STEP 1: Add imports at the top of web.py (after existing imports)
# =============================================================================

"""
from .auth import get_current_user, get_current_user_optional, authenticate_websocket
from .rate_limiter import rate_limit_middleware, cleanup_old_rate_limits
from .api.auth_endpoints import router as auth_router
from starlette.middleware.base import BaseHTTPMiddleware
"""

# =============================================================================
# STEP 2: Add middleware AFTER app = FastAPI() line
# =============================================================================

"""
# Security: HTTPS redirect in production
@app.middleware("http")
async def https_redirect_middleware(request: Request, call_next):
    # Force HTTPS in production
    if os.getenv('ENVIRONMENT') == 'production':
        if request.url.scheme == 'http':
            url = request.url.replace(scheme='https')
            return RedirectResponse(url=url, status_code=301)
    response = await call_next(request)
    return response

# Security: Rate limiting
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)

# Security: CORS - restrict to specific origins
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:3001').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # CHANGED FROM allow_origins=["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security: Add security headers
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Include authentication router
app.include_router(auth_router)
"""

# =============================================================================
# STEP 3: Protect existing trading endpoints - Example for /api/manual-trade
# =============================================================================

"""
# BEFORE (unprotected):
@app.post('/api/manual-trade')
async def api_manual_trade(...):
    ...

# AFTER (protected):
@app.post('/api/manual-trade')
async def api_manual_trade(
    ...,
    current_user: User = Depends(get_current_user)  # ADD THIS
):
    # Get user's API keys instead of using global keys
    from .encryption import get_api_keys
    keys = get_api_keys(current_user.id, 'binance', is_testnet=False)
    
    if not keys:
        raise HTTPException(
            status_code=400,
            detail="No API keys configured. Please add your Binance API keys first."
        )
    
    # Use user's keys
    exchange = ccxtpro.binance({
        'apiKey': keys['api_key'],
        'secret': keys['secret'],
        'enableRateLimit': True,
    })
    ...
"""

# =============================================================================
# STEP 4: Protect WebSocket endpoints - Example for /ws/live-dashboard
# =============================================================================

"""
# BEFORE (unprotected):
@app.websocket("/ws/live-dashboard")
async def websocket_live_dashboard(websocket: WebSocket):
    await websocket.accept()
    ...

# AFTER (protected):
@app.websocket("/ws/live-dashboard")
async def websocket_live_dashboard(websocket: WebSocket):
    # Authenticate before accepting connection
    user = await authenticate_websocket(websocket)
    
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    await websocket.accept()
    
    # Get user's API keys
    from .encryption import get_api_keys
    keys = get_api_keys(user.id, 'binance', is_testnet=False)
    
    if not keys:
        await websocket.send_json({
            "type": "error",
            "message": "No API keys configured"
        })
        await websocket.close()
        return
    
    # Use user's keys for WebSocket connection
    exchange = ccxtpro.binance({
        'apiKey': keys['api_key'],
        'secret': keys['secret'],
        'enableRateLimit': True,
    })
    ...
"""

# =============================================================================
# STEP 5: Add startup event for cleanup tasks
# =============================================================================

"""
@app.on_event("startup")
async def startup_event():
    # Schedule periodic cleanup of old rate limit records
    import asyncio
    
    async def cleanup_task():
        while True:
            await asyncio.sleep(86400)  # Run daily
            cleanup_old_rate_limits()
    
    asyncio.create_task(cleanup_task())
"""

# =============================================================================
# STEP 6: Add .env variables
# =============================================================================

"""
Create or update .env file with:

# Security
JWT_SECRET_KEY=your-secret-key-here-min-32-chars
ENCRYPTION_KEY=your-fernet-key-here
ENVIRONMENT=development  # or 'production'
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Existing Binance keys (for admin/demo only)
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
"""

print("""
=============================================================================
SECURITY INTEGRATION COMPLETE
=============================================================================

Next steps:
1. Install dependencies: pip install -r requirements.txt
2. Add the code snippets above to web.py
3. Update .env with JWT_SECRET_KEY and ENCRYPTION_KEY
4. Test authentication: POST /api/auth/register
5. Test login: POST /api/auth/login
6. Use Bearer token in headers: Authorization: Bearer <token>

Documentation created in this file.
=============================================================================
""")
