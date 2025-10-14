# ✅ Railway Staging Setup - Complete Checklist

**Date**: 2025-10-14  
**Status**: Ready to Deploy  

---

## 🎯 What You Have Now

### ✅ Generated Secrets

**JWT_SECRET_KEY for Staging**:
```
HJPspaGUl3ScsVpHCg7Sl64cfRDWImPdGYeRrBdBKY8
```

**⚠️ IMPORTANT**: Copy this key now! You'll need it for Railway environment variables.

### ✅ Files Created

1. **RAILWAY_STAGING_DEPLOYMENT.md**
   - Complete deployment guide
   - Step-by-step instructions
   - Environment variables list
   - Verification tests
   - Troubleshooting guide

2. **test_staging_deployment.ps1**
   - Automated verification script
   - Tests all security features
   - Runs 12 comprehensive tests
   - Provides detailed reports

3. **deploy_railway_staging.ps1**
   - Deployment helper script
   - Lists all environment variables
   - Quick reference guide

4. **.github/workflows/deploy-staging.yml**
   - GitHub Actions workflow
   - Automatic deployments on push
   - Health check verification
   - Deployment summaries

5. **AUTOMATIC_DEPLOYMENTS_SETUP.md**
   - GitHub Actions setup guide
   - Railway token instructions
   - Monitoring and troubleshooting

---

## 📋 Next Steps (In Order)

### Step 1: Complete Railway Setup (5 minutes)

Railway dashboard is already open in your browser!

**Do this now**:

1. **Create Service from GitHub**
   - Click **"+ New"** → **"GitHub Repo"**
   - Select: `dannyspk/arbitra-backend`
   - Branch: `development`
   - Service name: `arbitra-api-staging`

2. **Add Environment Variables**
   
   Copy these into Railway (Variables tab):
   
   ```bash
   ENVIRONMENT=staging
   REQUIRE_AUTH=true
   REQUIRE_HTTPS=true
   ENABLE_RATE_LIMITING=true
   ENABLE_WEBSOCKET_AUTH=true
   JWT_SECRET_KEY=HJPspaGUl3ScsVpHCg7Sl64cfRDWImPdGYeRrBdBKY8
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=60
   ENCRYPTION_KEY=b6q3t8Y11VkPm38OQA-CRDgpsqt7aIrA8MyyT6j9BK4=
   DATABASE_PATH=data/staging/security.db
   LOG_LEVEL=INFO
   ```
   
   **API Keys** (from .env.staging):
   ```bash
   BINANCE_API_KEY=mCKNY0bBb5ZjWDRGwUpynLuGum6wHEOdCWKieqZSPUv8Q4qwiYgWlwWTtXZtXP23
   BINANCE_API_SECRET=9mt3IjYLzzpUtJvpBESJRp1vKLjItxrMbyC0vSk8NrVYqrjL75tBGe3kQjBTmcGB
   LUNARCRUSH_API_KEY=lgt3s7f4mwl8nqik0kxdrizj5amgetoygaibzs78
   ```
   
   **Risk Settings**:
   ```bash
   ARB_MAX_POSITION_SIZE=100
   ARB_MAX_DAILY_TRADES=20
   ARB_MAX_LOSS_PERCENT=2
   ARB_ALLOW_LIVE_EXECUTION=1
   ARB_ALLOW_LIVE_ORDERS=1
   ALLOW_LIVE_ONCHAIN=0
   ```

3. **Deploy**
   - Click **"Deploy"** button
   - Wait 2-3 minutes for build
   - Note the generated URL (e.g., `https://arbitra-api-staging.up.railway.app`)

### Step 2: Test Deployment (2 minutes)

Once Railway shows "Deployed":

```powershell
# Update with your actual Railway URL
.\test_staging_deployment.ps1 -BaseUrl "https://arbitra-api-staging.up.railway.app"
```

**Expected**: 12/12 tests passing ✅

### Step 3: Set Up GitHub Actions (3 minutes)

1. **Get Railway Token**
   - Go to: https://railway.app/account/tokens
   - Create token: "GitHub Actions - Staging Deploy"
   - Copy token

2. **Add to GitHub Secrets**
   - Go to: https://github.com/dannyspk/arbitra-backend/settings/secrets/actions
   - New secret: `RAILWAY_TOKEN`
   - Paste token
   - Save

3. **Test Automatic Deployment**
   ```bash
   # Make a small change and push
   git commit --allow-empty -m "test: trigger auto-deploy"
   git push origin development
   ```
   
   - Watch: https://github.com/dannyspk/arbitra-backend/actions
   - Deployment should trigger automatically

---

## 🧪 Verification Commands

### Quick Health Check
```powershell
curl https://your-railway-url.up.railway.app/health
```

### Full Test Suite
```powershell
.\test_staging_deployment.ps1 -BaseUrl "https://your-railway-url.up.railway.app"
```

### View Logs
```bash
railway logs
```

---

## 📊 Success Metrics

Your staging deployment is successful when:

- ✅ Railway service deployed and running
- ✅ Health check returns `{"status": "healthy"}`
- ✅ API docs accessible at `/docs`
- ✅ User registration working (returns token)
- ✅ User login working (authenticates)
- ✅ Protected endpoints require auth (401 without token)
- ✅ Invalid tokens rejected
- ✅ API key encryption working
- ✅ Rate limiting enabled (429 on excessive requests)
- ✅ HTTPS enforced
- ✅ All 12 verification tests passing
- ✅ GitHub Actions deploying automatically

---

## 🎯 After Staging Works

Once staging is verified:

1. **Update Frontend**
   - Point to staging API URL
   - Test authentication flow
   - Deploy frontend to Vercel

2. **Security Audit**
   - Run full security scan
   - Test edge cases
   - Verify all endpoints protected

3. **Performance Testing**
   - Load test with k6
   - Monitor response times
   - Check database performance

4. **Production Deployment**
   - Create production environment
   - Generate NEW production secrets
   - Deploy with stricter security

---

## 🔒 Security Reminders

- ✅ JWT_SECRET_KEY is unique for staging
- ✅ ENCRYPTION_KEY is different from dev/prod
- ✅ Auth is REQUIRED (not optional like dev)
- ✅ HTTPS is ENFORCED
- ✅ Rate limiting is ENABLED
- ✅ WebSocket auth is ENABLED
- ⚠️ Never use staging keys in production
- ⚠️ Rotate secrets regularly
- ⚠️ Monitor audit logs

---

## 📁 Reference Files

| File | Purpose |
|------|---------|
| `RAILWAY_STAGING_DEPLOYMENT.md` | Full deployment guide |
| `test_staging_deployment.ps1` | Automated verification |
| `deploy_railway_staging.ps1` | Deployment helper |
| `.github/workflows/deploy-staging.yml` | Auto-deploy workflow |
| `AUTOMATIC_DEPLOYMENTS_SETUP.md` | GitHub Actions guide |
| `.env.staging` | Staging environment config |
| `railway.toml` | Railway deployment config |

---

## ✅ Completion Checklist

Track your progress:

- [ ] Railway service created from GitHub repo
- [ ] All environment variables configured in Railway
- [ ] JWT_SECRET_KEY set (HJPspaGUl3ScsVpHCg7Sl64cfRDWImPdGYeRrBdBKY8)
- [ ] Service deployed successfully
- [ ] Health check passing
- [ ] API docs accessible
- [ ] Verification script run (12/12 tests passing)
- [ ] Railway token generated
- [ ] GitHub secret RAILWAY_TOKEN configured
- [ ] Automatic deployment tested and working
- [ ] Staging URL documented
- [ ] Frontend updated with staging URL
- [ ] Security features verified
- [ ] Ready for production deployment

---

## 🎉 You're Ready!

Everything is prepared for staging deployment. Just follow the 3 steps above and you'll have:

- ✅ Fully functional staging environment
- ✅ Production-like security testing
- ✅ Automatic deployments from GitHub
- ✅ Comprehensive verification tests
- ✅ Ready for frontend integration

**Estimated time to complete**: 10 minutes

**Let's deploy!** 🚀

---

**Created**: 2025-10-14  
**Railway Project**: https://railway.com/project/09bc8d71-6ef3-4dea-b211-3e72ce75b8e8  
**GitHub Repo**: https://github.com/dannyspk/arbitra-backend
