# 🏗️ REPOSITORY & DEPLOYMENT STRATEGY

**Date:** October 14, 2025  
**Current Setup:** Single repo, single branch

---

## 📊 Current State

**Repository:** `github.com/dannyspk/arbitra-backend`  
**Branches:** `main` only  
**Environments:** Managed via `.env` files

---

## ✅ RECOMMENDED: Multi-Branch Strategy

### Branch Structure:
```
arbitra-backend/
├── main         → Production deployment
├── staging      → Pre-production testing
└── development  → Development & testing
```

### Deployment Flow:
```
development → staging → main
    ↓           ↓        ↓
  Railway     Railway  Railway
   (dev)     (staging) (prod)
```

---

## 🚀 Setup Instructions

### Step 1: Create Staging Branch
```powershell
# Create staging branch from main
git checkout -b staging
git push -u origin staging

# Verify
git branch -a
```

### Step 2: Create Development Branch
```powershell
# Create development branch from staging
git checkout staging
git checkout -b development
git push -u origin development

# Verify
git branch -a
```

### Step 3: Protect Main Branch (GitHub)
1. Go to: `https://github.com/dannyspk/arbitra-backend/settings/branches`
2. Add rule for `main` branch
3. Enable:
   - ✅ Require pull request reviews
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date

### Step 4: Configure Railway Deployments

#### Production (main branch):
```bash
Railway Project: arbitra-prod
GitHub Branch: main
Environment Variables: Use .env.production values
Domain: api.arbitra.com
```

#### Staging (staging branch):
```bash
Railway Project: arbitra-staging
GitHub Branch: staging
Environment Variables: Use .env.staging values
Domain: staging-api.arbitra.com
```

#### Development (development branch):
```bash
Railway Project: arbitra-dev
GitHub Branch: development
Environment Variables: Use .env.development values
Domain: dev-api.arbitra.com
```

---

## 🔄 Workflow

### Development → Staging:
```powershell
# Work on development branch
git checkout development
# Make changes, commit
git add .
git commit -m "Add feature X"
git push origin development

# Merge to staging for testing
git checkout staging
git merge development
git push origin staging

# Railway auto-deploys staging
# Test at: https://staging-api.arbitra.com
```

### Staging → Production:
```powershell
# After testing passes on staging
git checkout main
git merge staging
git push origin main

# Railway auto-deploys production
# Live at: https://api.arbitra.com
```

---

## 🎯 Environment Configuration Per Branch

### Development Branch (.env.development)
```bash
ENVIRONMENT=development
REQUIRE_AUTH=false          # Easier testing
REQUIRE_HTTPS=false         # Local HTTP allowed
ENABLE_RATE_LIMITING=false  # No limits in dev
DATABASE_PATH=data/dev/security.db
CORS_ORIGINS=*              # Allow all origins
```

### Staging Branch (.env.staging)
```bash
ENVIRONMENT=staging
REQUIRE_AUTH=true           # Test auth flow
REQUIRE_HTTPS=true          # Enforce HTTPS
ENABLE_RATE_LIMITING=true   # Test rate limits
DATABASE_PATH=data/staging/security.db
CORS_ORIGINS=https://staging.arbitra.com,http://localhost:3000
```

### Main Branch (.env.production)
```bash
ENVIRONMENT=production
REQUIRE_AUTH=true           # Full security
REQUIRE_HTTPS=true          # HTTPS only
ENABLE_RATE_LIMITING=true   # Full protection
DATABASE_PATH=data/prod/security.db
CORS_ORIGINS=https://arbitra.com,https://www.arbitra.com,https://app.arbitra.com
```

---

## 📋 Testing Strategy

### Local Testing (Your Machine):
```powershell
# Use development environment
.\switch_env.ps1 development

# Run locally
python main.py

# Test at: http://localhost:8000
```

### Integration Testing (Staging on Railway):
```powershell
# Push to staging branch
git checkout staging
git push origin staging

# Railway auto-deploys
# Test at: https://staging-api.arbitra.com

# Run integration tests
pytest tests/integration/
```

### Production Validation (Production on Railway):
```powershell
# Only deploy after staging tests pass
git checkout main
git merge staging
git push origin main

# Railway auto-deploys
# Monitor at: https://api.arbitra.com

# Run smoke tests
pytest tests/smoke/
```

---

## 🔒 Security Per Environment

| Feature | Development | Staging | Production |
|---------|-------------|---------|------------|
| Auth | Optional | Required | Required |
| HTTPS | No | Yes | Yes |
| Rate Limiting | No | Yes | Yes |
| CORS | Open (*) | Restricted | Strict |
| Logging | DEBUG | INFO | WARNING |
| Error Details | Full | Limited | Minimal |

---

## 🎯 Alternative: Simple Approach (Current Setup)

If you don't want branches, you can use a single repo with Railway environment variables:

### Railway Projects:
1. **arbitra-prod** - Points to `main`, uses production env vars
2. **arbitra-staging** - Points to `main`, uses staging env vars  
3. **arbitra-dev** - Points to `main`, uses development env vars

**Advantage:** Simplest setup  
**Disadvantage:** Can't test code changes before production

---

## 💡 Recommended: Hybrid Approach

**Use branches + environment variables:**

```
Branch: main → Railway Prod → .env.production values
Branch: staging → Railway Staging → .env.staging values
Branch: development → Railway Dev → .env.development values
```

This gives you:
- ✅ Code isolation (branches)
- ✅ Environment isolation (.env files)
- ✅ Safe testing (staging before prod)
- ✅ Easy rollback (git revert)
- ✅ Clear workflow (branch = environment)

---

## 🚀 Next Steps

1. **Create branches:**
   ```powershell
   git checkout -b staging
   git push -u origin staging
   git checkout -b development
   git push -u origin development
   ```

2. **Setup Railway projects:**
   - Create 3 Railway projects
   - Link each to a different branch
   - Configure environment variables

3. **Test the flow:**
   - Push to development → auto-deploy to dev
   - Merge to staging → auto-deploy to staging
   - Merge to main → auto-deploy to production

4. **Enable branch protection:**
   - Protect `main` branch
   - Require PR reviews
   - Run tests before merge

---

**Current Status:** ✅ Environment separation ready, branches needed for full workflow

**Would you like me to help set up the branches and Railway configuration?**
