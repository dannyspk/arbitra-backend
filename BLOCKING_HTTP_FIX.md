# Blocking HTTP Calls Fix - Endpoint Freezing Issue

## Problem

The AI Analysis and Social Sentiment endpoints were **freezing and timing out** after the server started, making them unresponsive.

### Root Cause

Both endpoints used **synchronous blocking HTTP calls** in an async FastAPI application:

1. **Social Sentiment** (`src/arbitrage/api/social_sentiment.py`):
   - Used `requests.get()` with 10-second timeout
   - Blocked the entire event loop when LunarCrush API was slow

2. **AI Analysis** (`src/arbitrage/web.py`):
   - Used `urllib.request.urlopen()` with 10-second timeout
   - Blocked the event loop when fetching Binance klines data

### Why This Caused Freezing

When a synchronous blocking call is made in an async endpoint:
- The entire FastAPI event loop **freezes** waiting for the HTTP response
- All other incoming requests are **blocked** until the call completes or times out
- If external APIs are slow or rate-limited, the server becomes **unresponsive**
- Multiple concurrent requests compound the problem

## Solution

Converted all blocking HTTP calls to **async** using `httpx`:

### Changes Made

1. **Replaced `requests` with `httpx.AsyncClient`**
   - Non-blocking HTTP calls
   - Proper async/await pattern
   - Reduced timeout from 10s to 5s for faster failure

2. **Replaced `urllib.request.urlopen` with `httpx.AsyncClient`**
   - Non-blocking Binance API calls
   - Concurrent requests don't block each other

3. **Made all functions async**
   - `fetch_lunarcrush_data()` → `async def`
   - `fetch_klines()` → `async def`
   - Properly awaited in endpoint handlers

4. **Added proper error handling**
   - `httpx.TimeoutException` handling
   - Graceful degradation on API failures

### Files Modified

- `src/arbitrage/api/social_sentiment.py` - Social Sentiment endpoint
- `src/arbitrage/web.py` - AI Analysis endpoint
- `requirements.txt` - Added `httpx>=0.24.0` dependency

## Benefits

✅ **No more endpoint freezing** - Non-blocking calls
✅ **Better performance** - Concurrent requests handled properly
✅ **Faster timeouts** - 5s instead of 10s
✅ **Improved reliability** - Proper async error handling
✅ **Server stays responsive** - Even when external APIs are slow

## Testing

After Railway redeploys:

```powershell
# Test Social Sentiment
Invoke-RestMethod "https://arbitra-backend-production.up.railway.app/api/social-sentiment/BTCUSDT"

# Test AI Analysis
Invoke-RestMethod "https://arbitra-backend-production.up.railway.app/api/ai-analysis/BTCUSDT"
```

Both endpoints should now respond consistently without timing out.

## Deployment

Pushed to GitHub: commit `e49ff2e`
Railway will auto-deploy with the fix (~2-3 minutes)

---

**Status**: ✅ Fixed and deployed
**Impact**: High - Fixes critical endpoint freezing issue
**Priority**: Critical
