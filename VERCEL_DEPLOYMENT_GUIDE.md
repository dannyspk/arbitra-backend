# Deploying to Vercel

This guide will walk you through deploying your Arbitrage Dashboard to Vercel.

## Prerequisites

1. **GitHub Account** - Your code needs to be on GitHub
2. **Vercel Account** - Sign up at [vercel.com](https://vercel.com)
3. **Backend API** - Your Python backend must be deployed and accessible via HTTPS

## Step 1: Prepare Your Backend API

Your frontend needs to communicate with your backend API. You have several options:

### Option A: Deploy Backend to a Cloud Provider

**Recommended Options:**
- **Railway** (easiest): https://railway.app
- **Render**: https://render.com
- **DigitalOcean App Platform**: https://www.digitalocean.com/products/app-platform
- **AWS EC2** (advanced): For production workloads

**Important:** Your backend must:
- Be accessible via HTTPS (not HTTP)
- Support CORS for your Vercel domain
- Have all required environment variables configured

### Option B: Local Development Only

If you're just testing and want to view the frontend publicly:
- Deploy frontend to Vercel
- Backend remains on your local machine (won't work for other users)
- Use ngrok or similar to expose localhost temporarily

## Step 2: Push Code to GitHub

### Initialize Git Repository (if not already done)

\`\`\`powershell
# Navigate to your frontend directory
cd C:\\arbitrage\\web\\frontend

# Initialize git
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit for Vercel deployment"
\`\`\`

### Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository (e.g., `arbitrage-dashboard`)
3. **Do NOT** initialize with README (you already have files)

### Push to GitHub

\`\`\`powershell
# Add remote (replace with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/arbitrage-dashboard.git

# Push to GitHub
git branch -M main
git push -u origin main
\`\`\`

## Step 3: Configure API URL

Before deploying, you need to decide how to handle the API URL.

### Current State
Your code has hardcoded API URLs like:
\`\`\`typescript
const API = 'http://127.0.0.1:8000'
\`\`\`

### Recommended Solution: Environment Variables

I've created a config file at `lib/config.ts`. You should update your components to use it:

\`\`\`typescript
import { getApiUrl } from '@/lib/config'

const API = getApiUrl()
\`\`\`

**Files that need updating** (optional but recommended):
- `app/page.tsx`
- `app/trading/page.tsx`
- `app/logs/page.tsx`
- `app/defi/page.tsx`
- `app/arbitrage/page.tsx`
- `app/balances/page.tsx`
- `components/ui/Topbar.tsx`
- `components/VaultAlertManager.tsx`
- `components/VaultHistoryChart.tsx`
- `components/SocialSentiment.tsx`
- `components/PositionTracker.tsx`
- `components/LiveDashboard.tsx`

## Step 4: Deploy to Vercel

### Method 1: Using Vercel Dashboard (Easiest)

1. **Go to Vercel**
   - Visit https://vercel.com
   - Click "Sign Up" or "Log In"
   - Sign in with GitHub

2. **Import Project**
   - Click "Add New..." → "Project"
   - Select your GitHub repository
   - Vercel will auto-detect it's a Next.js project

3. **Configure Project**
   - **Framework Preset:** Next.js (auto-detected)
   - **Root Directory:** Click "Edit" and set to `web/frontend`
   - **Build Command:** `npm run build` (default)
   - **Output Directory:** `.next` (default)
   - **Install Command:** `npm install` (default)

4. **Add Environment Variables**
   - Click "Environment Variables"
   - Add:
     - Name: `NEXT_PUBLIC_API_URL`
     - Value: Your backend API URL (e.g., `https://your-backend.railway.app`)
   - For all environments: Production, Preview, Development

5. **Deploy**
   - Click "Deploy"
   - Wait 1-3 minutes for deployment
   - You'll get a URL like: `https://your-app.vercel.app`

### Method 2: Using Vercel CLI

\`\`\`powershell
# Install Vercel CLI globally
npm install -g vercel

# Navigate to frontend directory
cd C:\\arbitrage\\web\\frontend

# Login to Vercel
vercel login

# Deploy (first time - it will ask configuration questions)
vercel

# For production deployment
vercel --prod
\`\`\`

**Answer the prompts:**
- Set up and deploy? **Y**
- Which scope? **Select your account**
- Link to existing project? **N**
- Project name? **arbitrage-dashboard** (or your preferred name)
- Directory? **./** (current directory)
- Override settings? **N**

## Step 5: Configure Environment Variables in Vercel

### Via Vercel Dashboard

1. Go to your project in Vercel dashboard
2. Click **Settings** → **Environment Variables**
3. Add:
   - **Key:** `NEXT_PUBLIC_API_URL`
   - **Value:** `https://your-backend-url.com`
   - **Environments:** Check all (Production, Preview, Development)
4. Click **Save**
5. Redeploy: Go to **Deployments** → click "..." on latest → "Redeploy"

### Via CLI

\`\`\`powershell
# Set environment variable
vercel env add NEXT_PUBLIC_API_URL

# When prompted, enter your backend URL
# Example: https://your-backend.railway.app

# Select environments: Production, Preview, Development
\`\`\`

## Step 6: Configure CORS on Backend

Your backend API needs to allow requests from your Vercel domain.

### Update your backend (Python/FastAPI) to include:

\`\`\`python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-app.vercel.app",
        "https://*.vercel.app",  # Allow all Vercel preview deployments
        "http://localhost:3000",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
\`\`\`

## Step 7: Test Your Deployment

1. **Visit your Vercel URL**: `https://your-app.vercel.app`
2. **Check browser console** (F12) for any errors
3. **Test wallet connection** (if using wallet features)
4. **Verify API calls** work (check Network tab in DevTools)

## Common Issues and Solutions

### Issue 1: API Calls Fail (CORS Error)

**Symptom:** Console shows CORS errors
\`\`\`
Access to fetch at 'https://your-backend.com' from origin 'https://your-app.vercel.app' has been blocked by CORS policy
\`\`\`

**Solution:** 
- Update backend CORS settings to include your Vercel domain
- Ensure backend is using HTTPS (not HTTP)

### Issue 2: Environment Variables Not Working

**Symptom:** API URL is still `http://127.0.0.1:8000`

**Solution:**
- Verify environment variable name starts with `NEXT_PUBLIC_`
- Redeploy after adding environment variables
- Check: Settings → Environment Variables in Vercel dashboard

### Issue 3: Build Fails

**Symptom:** Deployment fails during build

**Common Causes:**
- TypeScript errors → Fix in code
- Missing dependencies → Check `package.json`
- Wrong root directory → Should be `web/frontend`

**Solution:**
\`\`\`powershell
# Test build locally first
cd web/frontend
npm run build
\`\`\`

### Issue 4: 404 on Some Routes

**Symptom:** Direct navigation to routes shows 404

**Solution:** Next.js App Router handles this automatically, but verify:
- Files are in `app/` directory
- Named correctly (page.tsx, layout.tsx)

## Continuous Deployment

Once set up, Vercel automatically deploys:
- **Every push to main branch** → Production deployment
- **Every push to other branches** → Preview deployment
- **Every pull request** → Preview deployment

## Custom Domain (Optional)

1. Go to your project in Vercel
2. Click **Settings** → **Domains**
3. Add your custom domain
4. Update DNS records as instructed by Vercel

## Monitoring and Analytics

Vercel provides built-in:
- **Analytics** - View traffic and performance
- **Logs** - Debug issues
- **Speed Insights** - Performance metrics

Access from your project dashboard.

## Alternative: Frontend-Only Deployment

If you want to deploy just the frontend without a backend:

1. Deploy to Vercel as described above
2. Don't set `NEXT_PUBLIC_API_URL`
3. The app will work with static features only
4. API-dependent features will show loading/error states

## Cost

- **Vercel Hobby Plan:** FREE
  - Unlimited deployments
  - HTTPS included
  - Serverless Functions
  - Perfect for personal projects

- **Pro Plan:** $20/month
  - Team collaboration
  - More compute resources
  - Advanced analytics

## Next Steps

1. ✅ Push code to GitHub
2. ✅ Deploy backend (Railway, Render, etc.)
3. ✅ Deploy frontend to Vercel
4. ✅ Set environment variables
5. ✅ Test and verify
6. 🎉 Share your live URL!

## Support

- **Vercel Docs:** https://vercel.com/docs
- **Next.js Docs:** https://nextjs.org/docs
- **Vercel Discord:** https://vercel.com/discord

## Your Deployment Checklist

- [ ] Backend API is deployed and accessible via HTTPS
- [ ] Backend CORS is configured for Vercel domain
- [ ] Code is pushed to GitHub
- [ ] Vercel project is created and connected to GitHub
- [ ] Root directory is set to `web/frontend`
- [ ] Environment variable `NEXT_PUBLIC_API_URL` is set
- [ ] First deployment completed successfully
- [ ] Tested the live site
- [ ] Wallet connection works (if applicable)
- [ ] API calls are successful
- [ ] No console errors

---

**Your frontend will be available at:**
`https://your-app-name.vercel.app`

Enjoy your deployed app! 🚀
