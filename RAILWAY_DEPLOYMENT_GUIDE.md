# Backend Deployment Guide for Railway

## Prerequisites
- GitHub account
- Railway account (sign up at https://railway.app with GitHub)

## Step 1: Prepare Your Backend Repository

### Option A: Push Backend to Same Repository (Easiest)

Your backend is already in `c:\arbitrage\`. Let's push it to GitHub:

\`\`\`powershell
cd C:\arbitrage

# Initialize git if not already done
git init

# Add all files
git add .

# Commit
git commit -m "Add backend for deployment"

# Add remote (using the same repo)
git remote add origin https://github.com/dannyspk/arbitra.git

# Push to a new branch (backend)
git checkout -b backend
git push -u origin backend
\`\`\`

### Option B: Create Separate Backend Repository

1. Go to https://github.com/new
2. Create `arbitra-backend`
3. Push just the backend code

## Step 2: Deploy to Railway

### A. Sign Up / Login
1. Go to https://railway.app
2. Click "Login with GitHub"
3. Authorize Railway

### B. Create New Project
1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose `dannyspk/arbitra` (or your backend repo)
4. Railway will auto-detect Python

### C. Configure Environment Variables

Click on your deployed service → Variables → Add these:

\`\`\`
ARB_ALLOW_ORIGINS=https://arbitra.vercel.app,https://*.vercel.app,http://localhost:3000
PORT=8000
\`\`\`

**Optional environment variables** (if needed by your app):
\`\`\`
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
MEXC_API_KEY=your_key_here
MEXC_API_SECRET=your_secret_here
\`\`\`

### D. Get Your Deployment URL

After deployment completes (2-5 minutes), Railway will give you a URL like:
\`\`\`
https://arbitra-production.up.railway.app
\`\`\`

Copy this URL - you'll need it for Vercel!

## Step 3: Update Vercel Environment Variable

1. Go to https://vercel.com/dashboard
2. Select your `arbitra` project
3. Go to **Settings** → **Environment Variables**
4. Find `NEXT_PUBLIC_API_URL`
5. Update its value to your Railway URL:
   \`\`\`
   https://arbitra-production.up.railway.app
   \`\`\`
6. Save
7. Go to **Deployments** → Click "..." on latest → **Redeploy**

## Step 4: Test Your Deployment

### Test Backend Health
\`\`\`powershell
Invoke-RestMethod -Uri "https://YOUR-RAILWAY-URL.up.railway.app/health"
\`\`\`

Should return: `{"status": "ok"}` or similar

### Test Frontend
1. Visit your Vercel URL: `https://arbitra.vercel.app`
2. Open browser console (F12)
3. Check that API calls are going to Railway URL
4. Verify no CORS errors

## Step 5: Monitor Your Deployment

### Railway Dashboard
- View logs: Railway Dashboard → Your Service → Logs
- Monitor metrics: CPU, Memory, Network usage
- Check deployment status

### Vercel Dashboard  
- View deployment logs
- Check function invocations
- Monitor performance

## Files Created for Deployment

✅ **railway.toml** - Railway configuration
✅ **Procfile** - Process file for Railway/Render
✅ **runtime.txt** - Python version specification

## Common Issues & Solutions

### Issue 1: Import Errors on Railway

**Symptom:** `ModuleNotFoundError: No module named 'dotenv'`

**Solution:** Add to `requirements.txt`:
\`\`\`
python-dotenv>=0.19.0
\`\`\`

### Issue 2: CORS Errors

**Symptom:** Frontend can't connect to backend

**Solution:** Verify `ARB_ALLOW_ORIGINS` includes your Vercel domain:
\`\`\`
ARB_ALLOW_ORIGINS=https://arbitra.vercel.app,https://*.vercel.app
\`\`\`

### Issue 3: Port Binding Error

**Symptom:** Backend fails to start on Railway

**Solution:** Ensure using `$PORT` environment variable:
\`\`\`python
uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT
\`\`\`

### Issue 4: Build Fails

**Symptom:** Railway build fails with package errors

**Solution:** Check `requirements.txt` includes all dependencies

## Alternative: Deploy to Render

If you prefer Render over Railway:

1. Go to https://render.com
2. New → Web Service
3. Connect GitHub repo
4. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT`
   - **Environment:** Python 3.12
5. Add same environment variables
6. Deploy

## Cost Estimates

### Railway
- **Free Tier:** $5 credit/month (enough for small projects)
- **Hobby Plan:** $5/month (500 hours)
- **Pro Plan:** $20/month (usage-based)

### Render  
- **Free Tier:** Available (with limitations)
- **Starter:** $7/month
- **Standard:** $25/month

## Security Best Practices

1. **Never commit API keys** - Use environment variables
2. **Enable CORS only for your domains** - Don't use `*` in production
3. **Use HTTPS** - Both Railway and Vercel provide this automatically
4. **Monitor logs** - Check for suspicious activity
5. **Set rate limits** - Protect your API from abuse

## Next Steps After Deployment

- [ ] Backend deployed to Railway
- [ ] Railway URL obtained
- [ ] Vercel environment variable updated
- [ ] Vercel redeployed
- [ ] Tested both frontend and backend
- [ ] Checked browser console for errors
- [ ] Verified API calls working
- [ ] Monitored Railway logs

## Your URLs

**Frontend (Vercel):** https://arbitra.vercel.app
**Backend (Railway):** https://your-app.up.railway.app (you'll get this after deployment)
**GitHub Repo:** https://github.com/dannyspk/arbitra

---

**Ready to deploy!** Follow the steps above and your app will be live! 🚀
