# 🌿 BRANCH WORKFLOW GUIDE

**Date:** October 14, 2025  
**Status:** ✅ Branches created and pushed to GitHub

---

## ✅ Branch Structure Created

```
arbitra-backend (github.com/dannyspk/arbitra-backend)
├── main         → Production (deployed)
├── staging      → Pre-production testing
└── development  → Active development
```

**Current Branch:** `development` 🟢

---

## 🎯 Branch Purposes

### 🔴 main (Production)
- **Purpose:** Live production code
- **Environment:** `.env.production`
- **Deploy to:** Railway Production
- **Domain:** `api.arbitra.com`
- **Security:** FULL (auth required, HTTPS only, rate limits)
- **Database:** `data/prod/security.db`
- **Protected:** ⚠️ Requires PR review before merge

**Rules:**
- ❌ Never commit directly to main
- ✅ Only merge from staging after full testing
- ✅ Always create releases/tags
- ✅ Monitor errors closely after deployment

---

### 🟡 staging (Pre-Production)
- **Purpose:** Production-like testing environment
- **Environment:** `.env.staging`
- **Deploy to:** Railway Staging
- **Domain:** `staging-api.arbitra.com`
- **Security:** FULL (same as production)
- **Database:** `data/staging/security.db`
- **Testing:** Integration tests, UAT, smoke tests

**Rules:**
- ✅ Merge from development when features are ready
- ✅ Run full test suite before merging to main
- ✅ Test all security features
- ✅ Verify API integrations work

---

### 🟢 development (Active Development)
- **Purpose:** Day-to-day coding and experimentation
- **Environment:** `.env.development`
- **Deploy to:** Railway Dev (optional) or Local
- **Domain:** `dev-api.arbitra.com` or `localhost:8000`
- **Security:** RELAXED (auth optional, no HTTPS, no rate limits)
- **Database:** `data/dev/security.db`
- **Testing:** Unit tests, local integration tests

**Rules:**
- ✅ Commit freely during development
- ✅ Create feature branches from here
- ✅ Merge feature branches back here
- ✅ Keep it working (don't break the build)

---

## 🔄 Workflow Examples

### Daily Development Work

```powershell
# Start on development branch
git checkout development

# Make sure you're up to date
git pull origin development

# Make changes to code
# ... edit files ...

# Commit your work
git add .
git commit -m "feat: add new trading signal"

# Push to GitHub
git push origin development

# Railway auto-deploys to dev environment (if configured)
```

---

### Promoting to Staging

```powershell
# Switch to staging branch
git checkout staging

# Make sure staging is up to date
git pull origin staging

# Merge development changes
git merge development

# Resolve any conflicts if needed
# ... fix conflicts ...

# Push to GitHub
git push origin staging

# Railway auto-deploys to staging environment

# Test thoroughly at: https://staging-api.arbitra.com
# - Test authentication
# - Test rate limiting
# - Test all API endpoints
# - Run integration tests
```

---

### Deploying to Production

```powershell
# ONLY after staging tests pass!

# Switch to main branch
git checkout main

# Make sure main is up to date
git pull origin main

# Merge staging (NOT development!)
git merge staging

# Create a release tag
git tag -a v1.2.0 -m "Release version 1.2.0 - Add trading signals"

# Push to GitHub
git push origin main
git push origin v1.2.0

# Railway auto-deploys to production

# Monitor production:
# - Check error logs
# - Verify all endpoints working
# - Test critical user flows
# - Monitor performance metrics
```

---

### Hotfix (Emergency Production Fix)

```powershell
# Create hotfix branch from main
git checkout main
git checkout -b hotfix/critical-bug-fix

# Make the fix
# ... edit files ...

# Commit the fix
git add .
git commit -m "hotfix: fix critical trading bug"

# Merge directly to main (emergency only!)
git checkout main
git merge hotfix/critical-bug-fix
git push origin main

# Tag the hotfix
git tag -a v1.2.1 -m "Hotfix: critical bug"
git push origin v1.2.1

# Merge back to staging and development
git checkout staging
git merge main
git push origin staging

git checkout development
git merge staging
git push origin development

# Clean up hotfix branch
git branch -d hotfix/critical-bug-fix
```

---

### Feature Branch Workflow (Recommended)

```powershell
# Create feature branch from development
git checkout development
git checkout -b feature/api-key-management

# Work on feature
# ... make changes ...
git add .
git commit -m "feat: add API key encryption"

# Push feature branch
git push origin feature/api-key-management

# Create Pull Request on GitHub
# - Go to GitHub
# - Create PR: feature/api-key-management → development
# - Request code review
# - Wait for approval

# After PR approved, merge on GitHub
# Then update local development
git checkout development
git pull origin development

# Delete feature branch
git branch -d feature/api-key-management
git push origin --delete feature/api-key-management
```

---

## 🔍 Checking Current Branch

```powershell
# See which branch you're on
git branch

# See all branches (local + remote)
git branch -a

# See current status
git status
```

---

## 🚀 Railway Deployment Setup

### Create 3 Railway Projects:

#### 1. Production (main branch)
```bash
Project Name: arbitra-prod
GitHub Repo: dannyspk/arbitra-backend
GitHub Branch: main
Root Directory: .
Build Command: pip install -r requirements.txt
Start Command: python main.py

Environment Variables (from .env.production):
ENVIRONMENT=production
REQUIRE_AUTH=true
REQUIRE_HTTPS=true
... (all production values)
```

#### 2. Staging (staging branch)
```bash
Project Name: arbitra-staging
GitHub Repo: dannyspk/arbitra-backend
GitHub Branch: staging
Root Directory: .
Build Command: pip install -r requirements.txt
Start Command: python main.py

Environment Variables (from .env.staging):
ENVIRONMENT=staging
REQUIRE_AUTH=true
REQUIRE_HTTPS=true
... (all staging values)
```

#### 3. Development (development branch) - Optional
```bash
Project Name: arbitra-dev
GitHub Repo: dannyspk/arbitra-backend
GitHub Branch: development
Root Directory: .
Build Command: pip install -r requirements.txt
Start Command: python main.py

Environment Variables (from .env.development):
ENVIRONMENT=development
REQUIRE_AUTH=false
REQUIRE_HTTPS=false
... (all development values)
```

---

## 📋 Pre-Deployment Checklist

### Before Merging to Staging:
- [ ] All unit tests pass locally
- [ ] Code reviewed by team member (optional)
- [ ] No console.log or debug code left in
- [ ] Environment variables documented
- [ ] Database migrations tested

### Before Merging to Production:
- [ ] All staging tests pass
- [ ] Security features tested (auth, rate limits, HTTPS)
- [ ] Performance tested under load
- [ ] Error monitoring configured (Sentry)
- [ ] Backup database before deployment
- [ ] Rollback plan documented
- [ ] Team notified of deployment

---

## 🛡️ Branch Protection (Setup on GitHub)

### Protect `main` branch:
1. Go to: `https://github.com/dannyspk/arbitra-backend/settings/branches`
2. Click "Add rule"
3. Branch name pattern: `main`
4. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (1)
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - ✅ Include administrators (recommended)

### Protect `staging` branch (optional):
- Same as above but less strict
- Useful for team collaboration

---

## 🎯 Quick Reference Commands

```powershell
# Switch branches
git checkout main           # Go to production
git checkout staging        # Go to staging
git checkout development    # Go to development

# Update branch from remote
git pull origin main
git pull origin staging
git pull origin development

# See what changed
git diff main staging       # Compare main vs staging
git diff staging development # Compare staging vs development

# View commit history
git log --oneline --graph --all --decorate

# Undo last commit (local only, not pushed)
git reset --soft HEAD~1

# Switch environment locally
.\switch_env.ps1 development   # Dev mode
.\switch_env.ps1 staging       # Staging mode
.\switch_env.ps1 production    # Production mode
```

---

## 🔄 Deployment Flow Summary

```
development → staging → main
    ↓           ↓        ↓
  Local/     Railway   Railway
  Railway    Staging   Production
  (dev)

Features → Tests → Production
```

**Typical Timeline:**
- Development: Daily commits
- Staging: Weekly/bi-weekly promotions
- Production: Weekly/bi-weekly releases (after staging validation)

---

## ✅ Current Status

**Branches Created:**
- ✅ `main` - Production ready
- ✅ `staging` - Testing environment
- ✅ `development` - Active development (you are here)

**Environment Files:**
- ✅ `.env.development` - Development config
- ✅ `.env.testing` - Testing config
- ✅ `.env.staging` - Staging config
- ✅ `.env.production` - Production config

**Next Steps:**
1. ⏳ Set up Railway projects (3 environments)
2. ⏳ Configure environment variables on Railway
3. ⏳ Test deployments to each environment
4. ⏳ Enable GitHub branch protection
5. ⏳ Integrate security into web.py

---

**You're currently on: `development` branch** 🟢  
**Local environment: `development` mode**  
**Ready for development work!**
