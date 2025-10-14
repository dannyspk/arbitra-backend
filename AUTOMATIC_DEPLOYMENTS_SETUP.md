# 🤖 Automatic Railway Deployments Setup

This guide explains how to set up automatic deployments to Railway whenever you push to the `development` branch.

---

## 📋 Prerequisites

- [x] Railway project created (`cryptoaiedge`)
- [x] Railway service configured
- [x] GitHub repository (`dannyspk/arbitra-backend`)
- [ ] Railway API token generated
- [ ] GitHub secret configured

---

## 🔑 Step 1: Get Railway API Token

### Option A: Via Railway Dashboard (Recommended)

1. Go to: https://railway.app/account/tokens
2. Click **"Create Token"**
3. Name: `GitHub Actions - Staging Deploy`
4. Scope: Select your project (`cryptoaiedge`)
5. Click **"Create"**
6. **Copy the token immediately** (you won't see it again!)

### Option B: Via Railway CLI

```bash
railway whoami --token
```

**Important**: Save this token securely! You'll need it for GitHub.

---

## 🔒 Step 2: Add Secret to GitHub

1. Go to your repository: https://github.com/dannyspk/arbitra-backend
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Name: `RAILWAY_TOKEN`
5. Value: Paste the Railway token from Step 1
6. Click **"Add secret"**

---

## ✅ Step 3: Verify Setup

The GitHub Actions workflow is already created at:
```
.github/workflows/deploy-staging.yml
```

### Test the Workflow

**Automatic trigger** (when you push to `development`):
```bash
git add .
git commit -m "test: trigger automatic deployment"
git push origin development
```

**Manual trigger** (via GitHub UI):
1. Go to: https://github.com/dannyspk/arbitra-backend/actions
2. Select **"Deploy to Railway Staging"** workflow
3. Click **"Run workflow"**
4. Select branch: `development`
5. Click **"Run workflow"**

---

## 📊 Step 4: Monitor Deployment

### View in GitHub Actions

1. Go to: https://github.com/dannyspk/arbitra-backend/actions
2. Click on the latest workflow run
3. Watch the deployment progress live
4. Check the summary for health check results

### View in Railway Dashboard

1. Go to: https://railway.com/project/09bc8d71-6ef3-4dea-b211-3e72ce75b8e8
2. Click on your service
3. View **Deployments** tab
4. Check logs for deployment status

---

## 🔄 How It Works

### Workflow Triggers

The deployment workflow runs automatically when:

1. **Push to `development` branch** (automatic)
   - Excludes changes to: `.md` files, `docs/`, `.gitignore`, `LICENSE`
   
2. **Manual workflow dispatch** (manual trigger from GitHub UI)

### Deployment Steps

1. **Checkout code** - Pulls latest code from repository
2. **Deploy to Railway** - Triggers Railway deployment using API token
3. **Wait for deployment** - Gives Railway 30 seconds to deploy
4. **Health check** - Verifies `/health` endpoint returns 200
5. **Summary** - Posts deployment summary to GitHub Actions

### What Happens After Push

```
You push to development
         ↓
GitHub Actions triggers
         ↓
Code deployed to Railway
         ↓
Railway builds Docker image
         ↓
Railway runs health checks
         ↓
Service goes live
         ↓
GitHub Actions verifies health
         ↓
✅ Deployment complete!
```

**Time**: ~3-5 minutes from push to live

---

## 🐛 Troubleshooting

### Workflow Fails: "Invalid Railway Token"

**Issue**: Railway token is invalid or expired

**Fix**:
1. Generate new Railway token (Step 1)
2. Update GitHub secret `RAILWAY_TOKEN` (Step 2)
3. Re-run workflow

### Workflow Fails: "Health Check Failed"

**Issue**: Deployment succeeded but service not responding

**Fix**:
1. Check Railway logs for errors
2. Verify environment variables are set
3. Check database initialization
4. Ensure start command is correct in `railway.toml`

### Workflow Doesn't Trigger

**Issue**: Pushed to `development` but no workflow run

**Fix**:
1. Check you're on `development` branch
2. Verify workflow file exists: `.github/workflows/deploy-staging.yml`
3. Check if you only changed `.md` files (these are ignored)
4. Manually trigger workflow from GitHub UI

### Railway Service Not Found

**Issue**: GitHub Actions can't find Railway service

**Fix**:
1. Verify service name matches: `arbitra-api-staging`
2. Update service name in `.github/workflows/deploy-staging.yml` if different
3. Ensure Railway token has access to the project

---

## 🎯 Best Practices

### Branch Protection

**Recommended**: Protect `development` branch to require:
- Pull request reviews before merge
- Status checks to pass (including deployment)
- Up-to-date branch before merge

### Deployment Notifications

**Option 1**: Slack Notifications

Add to workflow:
```yaml
- name: 📢 Notify Slack
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "🚀 Staging deployment completed!"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

**Option 2**: Discord Notifications

Add to workflow:
```yaml
- name: 📢 Notify Discord
  uses: sarisia/actions-status-discord@v1
  with:
    webhook: ${{ secrets.DISCORD_WEBHOOK }}
    status: ${{ job.status }}
    title: "Staging Deployment"
```

### Rollback Strategy

If deployment fails:

1. **Automatic rollback** (Railway handles this)
2. **Manual rollback** (via Railway dashboard)
3. **Revert commit**:
   ```bash
   git revert HEAD
   git push origin development
   ```

---

## 📈 Advanced: Add Integration Tests

Enhance the workflow to run full test suite:

```yaml
- name: 🧪 Run integration tests
  run: |
    # Wait for deployment to be ready
    sleep 60
    
    # Run test script
    pwsh -File test_staging_deployment.ps1 -BaseUrl "https://arbitra-api-staging.up.railway.app"
```

This requires:
1. PowerShell installed on GitHub Actions runner
2. Test script available in repository
3. Proper test credentials configured

---

## 🔐 Security Notes

### Secrets Management

- ✅ **DO**: Store Railway token in GitHub Secrets
- ✅ **DO**: Use separate tokens per environment
- ✅ **DO**: Rotate tokens regularly
- ❌ **DON'T**: Commit tokens to Git
- ❌ **DON'T**: Share tokens between projects
- ❌ **DON'T**: Use production tokens for staging

### Token Permissions

Railway token should have:
- **Read** access to project
- **Write** access to deployments
- **No access** to billing or team settings

---

## 📊 Monitoring Deployments

### GitHub Actions Insights

View deployment history:
1. Go to repository **Actions** tab
2. Filter by workflow: "Deploy to Railway Staging"
3. View success/failure rates
4. Check deployment duration trends

### Railway Deployment History

View in Railway:
1. Project → Service → Deployments
2. See all deployments, build times, logs
3. Rollback to previous deployment if needed

---

## ✅ Verification Checklist

After setup, verify:

- [ ] Railway token generated and saved
- [ ] GitHub secret `RAILWAY_TOKEN` configured
- [ ] Workflow file committed to repository
- [ ] Test push triggers deployment
- [ ] Deployment completes successfully
- [ ] Health check passes
- [ ] Service accessible at Railway URL
- [ ] Logs show no errors

---

## 🎉 Success!

Once configured, every push to `development` will:

1. ✅ Automatically deploy to Railway staging
2. ✅ Run health checks
3. ✅ Provide deployment summary
4. ✅ Notify you of success/failure

**No manual deployment needed!** 🚀

---

## 📞 Support

- **Railway Docs**: https://docs.railway.app/develop/deployments
- **GitHub Actions**: https://docs.github.com/en/actions
- **Railway Discord**: https://discord.gg/railway

---

**Created**: 2025-10-14  
**Status**: Ready to configure
