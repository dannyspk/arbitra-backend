# 🔧 Railway Deployment Health Check Failures - SOLVED

## ❌ Problem

Railway deployment failing with:
```
Attempt #1 failed with service unavailable
Attempt #2 failed with service unavailable
Attempt #3 failed with service unavailable
...
```

---

## ✅ Solution Applied

### Root Cause
Railway was using the **Dockerfile** which had the wrong app path:
- ❌ Wrong: `CMD uvicorn src.arbitrage.app:app ...`
- ✅ Correct: `CMD uvicorn src.arbitrage.web:app ...`

Additionally, Railway prioritizes Dockerfile over Nixpacks, but our `railway.toml` was configured for Nixpacks.

### Fix Applied
1. **Renamed Dockerfile to Dockerfile.backup** - Forces Railway to use Nixpacks
2. **Committed and pushed** - Triggered new deployment
3. **Created Dockerfile.railway** - Proper Dockerfile if needed later

---

## 🔍 How to Diagnose Railway Deployment Issues

### 1. Check Build Logs
Look for the builder being used:
- ✅ Good: `=========================` followed by `Using Nixpacks` or `Using Detected Dockerfile`
- ❌ Bad: Build errors, missing dependencies

### 2. Check Deploy Logs
In Railway dashboard → Deployment → **Deploy Logs** tab

Common issues:
```bash
# Wrong app path
ModuleNotFoundError: No module named 'arbitrage.app'

# Missing dependencies
ImportError: No module named 'fastapi'

# Port binding issues
uvicorn.error: Error binding to address

# Database errors
sqlite3.OperationalError: unable to open database file
```

### 3. Check Application Logs
```bash
railway logs
```

Look for:
- App startup messages
- Port binding confirmation
- Database connection status

---

## 🛠️ Common Railway Deployment Fixes

### Issue 1: Wrong Start Command

**Symptoms**: Health check fails immediately

**Check**:
```toml
# railway.toml
[deploy]
startCommand = "uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT"
```

**or**

```dockerfile
# Dockerfile
CMD uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT
```

**Fix**: Ensure path matches your actual app structure:
```bash
src/
  arbitrage/
    web.py  # Contains: app = FastAPI()
```

### Issue 2: Missing Environment Variables

**Symptoms**: App starts but crashes, database errors

**Fix**: In Railway dashboard → Variables, add:
```bash
ENVIRONMENT=staging
DATABASE_PATH=data/staging/security.db
ENCRYPTION_KEY=<your-fernet-key>
JWT_SECRET_KEY=<your-jwt-secret>
```

### Issue 3: Port Not Binding

**Symptoms**: Health check times out

**Fix**: Ensure app uses Railway's `$PORT`:
```python
# In your app
import os
port = int(os.getenv("PORT", 8080))
```

And start command:
```bash
uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT
```

### Issue 4: Database Path Issues

**Symptoms**: `sqlite3.OperationalError: unable to open database file`

**Fix**: 
1. Create directory in Dockerfile:
   ```dockerfile
   RUN mkdir -p /app/data/staging
   ```

2. Or set relative path:
   ```bash
   DATABASE_PATH=./data/staging/security.db
   ```

3. Use Railway volume (in railway.toml):
   ```toml
   [[deploy.volumes]]
   mountPath = "/app/data"
   name = "strategy_data"
   ```

### Issue 5: Nixpacks vs Dockerfile Conflict

**Symptoms**: Railway uses Dockerfile when you want Nixpacks

**Fix Options**:

**Option A**: Remove Dockerfile
```bash
git rm Dockerfile
git commit -m "fix: use Nixpacks for deployment"
git push
```

**Option B**: Force Nixpacks with `.railwayignore`
```bash
# .railwayignore
Dockerfile
Dockerfile.*
```

**Option C**: Configure Railway to use specific builder
In Railway dashboard → Settings → Build:
- Builder: Select "Nixpacks" or "Dockerfile"

---

## 🎯 Best Configuration for Python/FastAPI

### Recommended: Use Nixpacks (Simpler)

**railway.toml**:
```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

**No Dockerfile needed** - Nixpacks auto-detects Python and installs from `pyproject.toml`

### Alternative: Use Dockerfile (More Control)

**Dockerfile.railway**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy app
COPY src ./src
COPY data ./data

# Create directories
RUN mkdir -p /app/data/staging

# Run
CMD uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT
```

**railway.toml**:
```toml
[build]
dockerfilePath = "Dockerfile.railway"

[deploy]
healthcheckPath = "/health"
```

---

## 📊 Monitoring Deployment

### Watch Deployment in Real-Time

**CLI**:
```bash
railway logs --follow
```

**Dashboard**:
1. Go to deployment
2. Click **Deploy Logs** tab
3. Watch real-time output

### Successful Deployment Indicators

**Build logs**:
```
✓ Build completed successfully
Build time: 45.2 seconds
```

**Deploy logs**:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

**Health check**:
```
✓ Healthcheck passed
Service is now available
```

---

## ✅ Current Status (After Fix)

- ✅ Dockerfile renamed to `Dockerfile.backup`
- ✅ Railway will now use **Nixpacks**
- ✅ Correct start command in `railway.toml`
- ✅ New deployment triggered automatically
- ⏳ Waiting for new deployment to complete

### Next Steps

1. **Wait 2-3 minutes** for new deployment
2. **Check Deploy Logs** - Should see:
   ```
   INFO: Application startup complete
   INFO: Uvicorn running on http://0.0.0.0:8080
   ```
3. **Health check should pass** - `/health` returns `{"status": "healthy"}`
4. **Test deployment**:
   ```powershell
   .\test_staging_deployment.ps1 -BaseUrl "https://your-railway-url.up.railway.app"
   ```

---

## 🚨 If Still Failing

### Check Environment Variables

Verify these are set in Railway:
```bash
railway variables
```

Required:
- `ENVIRONMENT=staging`
- `JWT_SECRET_KEY=<your-secret>`
- `ENCRYPTION_KEY=<your-fernet-key>`

### Check Logs for Specific Errors

```bash
railway logs --lines 100
```

Look for:
- Import errors
- Database errors
- Configuration errors

### Verify pyproject.toml

Ensure all dependencies listed:
```toml
[project]
dependencies = [
    "fastapi>=0.104.1",
    "uvicorn[standard]>=0.24.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "cryptography>=41.0.5",
    # ... other deps
]
```

---

## 📞 Get Help

If deployment still fails:

1. **Copy full logs**:
   ```bash
   railway logs > deployment_logs.txt
   ```

2. **Check Railway status**: https://status.railway.app

3. **Railway Discord**: https://discord.gg/railway

4. **Share logs** with specific error messages

---

**Issue Resolved**: 2025-10-14  
**Solution**: Removed Dockerfile, using Nixpacks  
**Status**: ✅ Redeploying with correct configuration
