# CRITICAL FIX: Server Freezing After Few Minutes

## Problem Identified

The server works fine for a few minutes after restart, then becomes completely unresponsive. HTTP endpoints timeout, and the server appears frozen.

## Root Cause

**Background position monitoring task using blocking HTTP calls:**

1. `_monitor_positions()` runs every 5 seconds
2. For each position, it fetches current price from Binance
3. Used `_fetch_ticker_sync()` which calls `urllib.request.urlopen()` - **BLOCKING!**
4. Even wrapped in `asyncio.to_thread()`, multiple concurrent calls create a bottleneck
5. Event loop gets overwhelmed with queued blocking operations
6. Server becomes unresponsive after a few minutes

### Code Path:
```
_monitor_positions() 
  → await asyncio.to_thread(_fetch_ticker_sync, ...)
    → _http_get_json_sync(url)
      → urllib.request.urlopen()  ← BLOCKING CALL!
```

## The Fix

**Converted to fully async HTTP calls using httpx:**

### Changes Made:

1. **Created `_fetch_ticker_async()`** (new async function)
   - Uses `httpx.AsyncClient()` instead of urllib
   - True async, non-blocking HTTP calls
   - Reduced timeout from 10s to 3s
   - Proper error handling with `httpx.TimeoutException`

2. **Updated `_monitor_positions()`**
   - Changed from: `await asyncio.to_thread(_fetch_ticker_sync, ...)`
   - Changed to: `await _fetch_ticker_async(...)`
   - Direct async call, no thread pool needed

3. **Kept `_fetch_ticker_sync()` for backward compatibility**
   - Marked as deprecated
   - Will be removed in future cleanup

### Other Async Fixes Included:

- **Social Sentiment** (`/api/social-sentiment`) - Converted to httpx
- **AI Analysis** (`/api/ai-analysis`) - Converted to httpx
- **Preview Hedge** (`/api/preview-hedge`) - Converted to httpx
- **WebSocket Ticker Watchers** - Added max restart limits to prevent infinite loops

## Files Modified:

- `src/arbitrage/web.py`
  - Line 4203: Added `_fetch_ticker_async()`
  - Line 6192-6197: Updated `_monitor_positions()` to use async version
  - Line 218: Fixed AI Analysis endpoint
  - Line 4803: Fixed Preview Hedge endpoint
  - Line 6822: Added WebSocket timeout and restart limits

- `src/arbitrage/api/social_sentiment.py`
  - Converted `fetch_lunarcrush_data()` to async with httpx

- `requirements.txt`
  - Added `httpx>=0.24.0`

## Testing

After restarting the server with these fixes:

1. **Server should stay responsive indefinitely**
2. **HTTP endpoints should respond consistently**
3. **Position monitoring should work without blocking**
4. **Multiple concurrent requests should be handled smoothly**

### Test Commands:

```powershell
# Test health endpoint repeatedly
1..100 | ForEach-Object { 
    $start = Get-Date
    Invoke-RestMethod "http://127.0.0.1:8000/health" | Out-Null
    $duration = ((Get-Date) - $start).TotalSeconds
    Write-Host "Request $_: $([math]::Round($duration, 2))s"
    Start-Sleep -Milliseconds 500
}

# Test AI Analysis (previously would freeze)
Invoke-RestMethod "http://127.0.0.1:8000/api/ai-analysis/BTCUSDT"

# Test Social Sentiment (previously would freeze)
Invoke-RestMethod "http://127.0.0.1:8000/api/social-sentiment/BTC"

# Test Funding Rate (previously would freeze)
Invoke-RestMethod "http://127.0.0.1:8000/api/preview-hedge?symbol=BTCUSDT"
```

## Next Steps

1. **Restart the server** to apply fixes
2. **Test for 10-15 minutes** to ensure stability
3. **Monitor the logs** - should see no WebSocket restart loops
4. **Test all endpoints** - should respond quickly
5. **Once stable, commit and deploy to Railway**

## Expected Behavior After Fix:

✅ Server stays responsive for hours/days  
✅ HTTP endpoints respond in < 1 second  
✅ Position monitoring works smoothly  
✅ No WebSocket infinite restart loops  
✅ All async operations are truly non-blocking  

---

**Status**: ✅ Fixed, ready for testing  
**Priority**: CRITICAL - Server stability  
**Impact**: HIGH - Fixes server freezing issue  
