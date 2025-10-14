# 🚀 Railway Staging Deployment Guide

**Status**: Ready to Deploy  
**Project**: cryptoaiedge  
**Environment**: Staging (Production-like testing)  
**Branch**: development  
**Railway Project ID**: 09bc8d71-6ef3-4dea-b211-3e72ce75b8e8

---

## 📋 Pre-Deployment Checklist

- [x] Railway CLI installed (`@railway/cli`)
- [x] Logged into Railway account (danish_javed@live.com)
- [x] Railway project created (`cryptoaiedge`)
- [x] Project linked to local directory
- [x] `railway.toml` configuration file ready
- [x] Environment variables prepared from `.env.staging`
- [ ] GitHub repository connected to Railway
- [ ] Service created in Railway
- [ ] Environment variables set
- [ ] JWT_SECRET_KEY generated and set
- [ ] Initial deployment triggered

---

## 🔧 Step-by-Step Deployment

### Step 1: Access Railway Dashboard

1. Go to: https://railway.com/project/09bc8d71-6ef3-4dea-b211-3e72ce75b8e8
2. Login with: danish_javed@live.com
3. Select environment: **production** (we'll configure it as staging)

### Step 2: Create Service from GitHub

1. Click **"+ New"** → **"GitHub Repo"**
2. Select repository: **dannyspk/arbitra-backend**
3. Branch: **development**
4. Service name: **arbitra-api-staging**

Railway will automatically detect:
- Language: Python
- Builder: Nixpacks
- Start command: From `railway.toml`

### Step 3: Configure Environment Variables

Go to **Variables** tab and add the following:

#### 🔐 Security Settings (CRITICAL)
```bash
ENVIRONMENT=staging
REQUIRE_AUTH=true
REQUIRE_HTTPS=true
ENABLE_RATE_LIMITING=true
ENABLE_WEBSOCKET_AUTH=true
```

#### 🔑 Authentication Settings
```bash
JWT_SECRET_KEY=<GENERATE_NEW_SECRET_FOR_STAGING>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

**⚠️ IMPORTANT**: Generate a NEW JWT_SECRET_KEY for staging:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 🔒 Encryption Key
```bash
ENCRYPTION_KEY=b6q3t8Y11VkPm38OQA-CRDgpsqt7aIrA8MyyT6j9BK4=
```

#### 💾 Database
```bash
DATABASE_PATH=data/staging/security.db
```

#### 🌐 CORS Configuration
```bash
CORS_ORIGINS=https://staging.arbitra.com,https://staging-app.arbitra.com,http://localhost:3000
```

**Note**: Update with your actual staging domain when available.

#### 📊 API Keys
```bash
BINANCE_API_KEY=mCKNY0bBb5ZjWDRGwUpynLuGum6wHEOdCWKieqZSPUv8Q4qwiYgWlwWTtXZtXP23
BINANCE_API_SECRET=9mt3IjYLzzpUtJvpBESJRp1vKLjItxrMbyC0vSk8NrVYqrjL75tBGe3kQjBTmcGB
LUNARCRUSH_API_KEY=lgt3s7f4mwl8nqik0kxdrizj5amgetoygaibzs78
```

#### ⚙️ Risk Management
```bash
ARB_MAX_POSITION_SIZE=100
ARB_MAX_DAILY_TRADES=20
ARB_MAX_LOSS_PERCENT=2
ARB_ALLOW_LIVE_EXECUTION=1
ARB_ALLOW_LIVE_ORDERS=1
ALLOW_LIVE_ONCHAIN=0
```

#### 📝 Logging
```bash
LOG_LEVEL=INFO
```

### Step 4: Configure Persistent Volume

Railway will automatically mount the volume from `railway.toml`:
- **Mount Path**: `/app/data`
- **Volume Name**: `strategy_data`
- **Purpose**: Persist SQLite database across restarts

Verify this in the **Settings** → **Volumes** tab.

### Step 5: Deploy

1. Click **"Deploy"** button
2. Wait for build to complete (~2-3 minutes)
3. Check deployment logs for errors
4. Note the generated URL (e.g., `https://arbitra-api-staging.up.railway.app`)

---

## ✅ Post-Deployment Verification

### Test 1: Health Check
```bash
curl https://arbitra-api-staging.up.railway.app/health
```

**Expected response**:
```json
{"status": "healthy"}
```

### Test 2: API Documentation
Visit: `https://arbitra-api-staging.up.railway.app/docs`

**Should see**: FastAPI Swagger UI with all endpoints

### Test 3: User Registration (via PowerShell)
```powershell
$body = @{
    username = "staging_test_user"
    email = "test@staging.arbitra.com"
    password = "TestPassword123!"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "https://arbitra-api-staging.up.railway.app/api/auth/register" -Method Post -Body $body -ContentType "application/json"

Write-Host "✅ Registration successful!"
Write-Host "User ID: $($response.id)"
Write-Host "Token: $($response.access_token)"
```

### Test 4: User Login
```powershell
$body = @{
    username = "staging_test_user"
    password = "TestPassword123!"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "https://arbitra-api-staging.up.railway.app/api/auth/login" -Method Post -Body $body -ContentType "application/json"

Write-Host "✅ Login successful!"
$token = $response.access_token
```

### Test 5: Protected Endpoint (Get User Info)
```powershell
$headers = @{
    "Authorization" = "Bearer $token"
}

$response = Invoke-RestMethod -Uri "https://arbitra-api-staging.up.railway.app/api/auth/me" -Method Get -Headers $headers

Write-Host "✅ Protected endpoint accessible!"
Write-Host "Username: $($response.username)"
Write-Host "Email: $($response.email)"
```

### Test 6: Rate Limiting (should be ENABLED in staging)
```powershell
# Rapid-fire requests to test rate limiting
1..20 | ForEach-Object {
    try {
        Invoke-RestMethod -Uri "https://arbitra-api-staging.up.railway.app/health"
        Write-Host "Request $_ : ✅"
    } catch {
        Write-Host "Request $_ : ❌ Rate limited (expected!)" -ForegroundColor Yellow
    }
}
```

**Expected**: Some requests should fail with 429 status code (rate limited).

### Test 7: HTTPS Enforcement
Try accessing via HTTP:
```bash
curl http://arbitra-api-staging.up.railway.app/health
```

**Expected**: Should redirect to HTTPS or reject (depending on Railway config).

---

## 📊 Monitoring & Logs

### View Logs
**Railway Dashboard**:
1. Go to project → service
2. Click **"Logs"** tab
3. Monitor real-time logs

**CLI**:
```bash
railway logs
```

### Key Metrics to Monitor
- **Response Time**: Should be < 200ms for most endpoints
- **Error Rate**: Should be < 1%
- **Memory Usage**: Should be stable (no leaks)
- **Database Size**: Monitor `/app/data/staging/security.db`

---

## 🔒 Security Validation

After deployment, verify security features:

### ✅ Authentication Required
- [ ] Cannot access `/api/auth/me` without token
- [ ] Cannot access `/api/user/api-keys` without token
- [ ] Cannot execute trades without authentication

### ✅ HTTPS Required
- [ ] HTTP requests redirect to HTTPS
- [ ] SSL certificate valid

### ✅ Rate Limiting Enabled
- [ ] Excessive requests get 429 status
- [ ] Rate limits reset after cooldown

### ✅ WebSocket Authentication
- [ ] WebSocket connections require valid token
- [ ] Invalid tokens rejected

### ✅ CORS Configured
- [ ] Only allowed origins can make requests
- [ ] Wildcard (*) NOT present in CORS_ORIGINS

---

## 🐛 Troubleshooting

### Issue: Build Fails
**Check**:
- Python version compatibility (3.12)
- Dependencies in `pyproject.toml`
- Nixpacks buildpack settings

**Fix**:
```bash
railway logs --deployment <deployment-id>
```

### Issue: Database Not Persisting
**Check**:
- Volume mount path matches `DATABASE_PATH`
- Volume named `strategy_data` exists
- Permission issues

**Fix**:
Verify in Railway dashboard → Settings → Volumes

### Issue: 500 Errors on Auth Endpoints
**Check**:
- `ENCRYPTION_KEY` is valid Fernet key
- `JWT_SECRET_KEY` is set
- Database initialized properly

**Fix**:
```bash
railway run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Issue: CORS Errors
**Check**:
- `CORS_ORIGINS` includes your frontend domain
- No trailing slashes in origins
- Protocol (http/https) matches

**Fix**:
Update `CORS_ORIGINS` variable in Railway dashboard.

---

## 🔄 Update/Redeploy

### Automatic Deployment (Recommended)
Railway automatically deploys when you push to `development` branch:

```bash
git add .
git commit -m "feat: update staging features"
git push origin development
```

Railway will:
1. Detect push
2. Build new image
3. Run health checks
4. Deploy if successful
5. Rollback if failed

### Manual Deployment
```bash
railway up
```

---

## 📈 Next Steps After Staging

1. **Frontend Integration**
   - Update frontend API URL to staging endpoint
   - Test authentication flow end-to-end
   - Deploy frontend to Vercel/Railway

2. **Load Testing**
   - Use k6 or Apache Bench
   - Test with 100+ concurrent users
   - Monitor performance metrics

3. **Security Audit**
   - Run OWASP ZAP scan
   - Check for SQL injection vulnerabilities
   - Verify all endpoints protected

4. **Production Deployment**
   - Create separate production environment
   - Generate NEW production secrets
   - Set stricter rate limits
   - Enable monitoring/alerting

---

## 🎯 Success Criteria

Staging deployment is successful when:

- ✅ All 10 security integration tests pass
- ✅ Health check returns 200
- ✅ User registration/login working
- ✅ Protected endpoints require auth
- ✅ Rate limiting active and working
- ✅ Database persists across restarts
- ✅ HTTPS enforced
- ✅ CORS properly configured
- ✅ Logs show no critical errors
- ✅ Frontend can connect and authenticate

---

## 📞 Support

**Railway Documentation**: https://docs.railway.app/  
**Railway Discord**: https://discord.gg/railway  
**Project Dashboard**: https://railway.com/project/09bc8d71-6ef3-4dea-b211-3e72ce75b8e8

---

**Created**: 2025-10-14  
**Last Updated**: 2025-10-14  
**Deployment Status**: 🟡 Pending (ready to deploy)
