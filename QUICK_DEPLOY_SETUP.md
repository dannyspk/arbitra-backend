# Quick Setup for Vercel Deployment

This script will help you prepare your project for deployment.

## Step 1: Update API URLs to use Environment Variables

Instead of manually updating each file, you can use this PowerShell script:

\`\`\`powershell
# Save this as update-api-urls.ps1
$files = @(
    "app/page.tsx",
    "app/trading/page.tsx",
    "app/logs/page.tsx",
    "app/defi/page.tsx",
    "app/arbitrage/page.tsx",
    "app/balances/page.tsx",
    "components/ui/Topbar.tsx",
    "components/VaultAlertManager.tsx",
    "components/VaultHistoryChart.tsx",
    "components/SocialSentiment.tsx",
    "components/PositionTracker.tsx",
    "components/LiveDashboard.tsx"
)

foreach ($file in $files) {
    $path = "C:\\arbitrage\\web\\frontend\\$file"
    if (Test-Path $path) {
        Write-Host "Updating $file..."
        # This is a preview - manual update recommended for accuracy
        Get-Content $path | Select-String "127.0.0.1:8000" | Select-Object LineNumber, Line
    }
}
\`\`\`

## Step 2: Quick Start Commands

\`\`\`powershell
# Navigate to frontend directory
cd C:\\arbitrage\\web\\frontend

# Install dependencies (if not already done)
npm install

# Test build locally
npm run build

# Run locally to test
npm run dev

# Initialize git repository
git init
git add .
git commit -m "Prepare for Vercel deployment"

# Create GitHub repo and push
# (Follow instructions in VERCEL_DEPLOYMENT_GUIDE.md)
\`\`\`

## Step 3: Environment Variable Reference

### Local Development (.env.local)
\`\`\`
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
\`\`\`

### Vercel Production
\`\`\`
NEXT_PUBLIC_API_URL=https://your-backend-api.com
\`\`\`

## Step 4: Quick Deploy with Vercel CLI

\`\`\`powershell
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy to preview
vercel

# Deploy to production
vercel --prod
\`\`\`

## Backend Deployment Options

### Railway (Recommended - Easiest)
1. Go to https://railway.app
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repo
5. Railway auto-detects Python/FastAPI
6. Add environment variables
7. Get your deployment URL

### Render
1. Go to https://render.com
2. Sign up
3. New → Web Service
4. Connect GitHub repo
5. Configure build/start commands
6. Deploy

### DigitalOcean App Platform
1. Go to https://cloud.digitalocean.com/apps
2. Create → App
3. Connect GitHub
4. Configure
5. Deploy

## Testing Checklist

- [ ] `npm run build` completes without errors
- [ ] All pages load correctly in `npm run dev`
- [ ] No TypeScript errors
- [ ] Environment variables are configured
- [ ] Backend API is accessible and has CORS configured
- [ ] Ready to deploy!

## Need Help?

See the full guide: `VERCEL_DEPLOYMENT_GUIDE.md`
