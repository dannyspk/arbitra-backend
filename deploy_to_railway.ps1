#!/usr/bin/env pwsh
# Deploy to Railway - Install CLI and deploy

Write-Host "`n🚂 Railway Deployment Script" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host ""

# Check if Railway CLI is installed
$railwayInstalled = Get-Command railway -ErrorAction SilentlyContinue

if (-not $railwayInstalled) {
    Write-Host "❌ Railway CLI not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Installing Railway CLI..." -ForegroundColor Yellow
    
    # Install via npm
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host "Installing via npm..." -ForegroundColor Cyan
        npm install -g @railway/cli
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Railway CLI installed successfully!" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to install Railway CLI" -ForegroundColor Red
            Write-Host ""
            Write-Host "Please install manually:" -ForegroundColor Yellow
            Write-Host "  npm install -g @railway/cli" -ForegroundColor White
            Write-Host ""
            Write-Host "Or use the Railway dashboard:" -ForegroundColor Yellow
            Write-Host "  https://railway.app/dashboard" -ForegroundColor Cyan
            exit 1
        }
    } else {
        Write-Host "❌ npm not found. Please install Node.js first." -ForegroundColor Red
        Write-Host ""
        Write-Host "Alternative: Use Railway Dashboard" -ForegroundColor Yellow
        Write-Host "  1. Go to https://railway.app/dashboard" -ForegroundColor White
        Write-Host "  2. Select your arbitra-backend project" -ForegroundColor White
        Write-Host "  3. Click 'Deploy' or 'Redeploy'" -ForegroundColor White
        exit 1
    }
}

Write-Host "✅ Railway CLI found" -ForegroundColor Green
Write-Host ""

# Check if logged in
Write-Host "Checking Railway login status..." -ForegroundColor Cyan
railway whoami 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Not logged in to Railway" -ForegroundColor Red
    Write-Host ""
    Write-Host "Logging in to Railway..." -ForegroundColor Yellow
    railway login
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Login failed" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Logged in to Railway" -ForegroundColor Green
Write-Host ""

# Check if project is linked
Write-Host "Checking project status..." -ForegroundColor Cyan
railway status 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Project not linked" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Linking project..." -ForegroundColor Cyan
    railway link
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to link project" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Project linked" -ForegroundColor Green
Write-Host ""

# Deploy
Write-Host "🚀 Deploying to Railway..." -ForegroundColor Cyan
Write-Host ""

railway up

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Deployment triggered successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Wait 2-3 minutes for deployment to complete" -ForegroundColor White
    Write-Host "  2. Run: .\check_railway_ip.ps1" -ForegroundColor White
    Write-Host "  3. Add the IP to Binance whitelist" -ForegroundColor White
    Write-Host ""
    Write-Host "Monitor deployment at:" -ForegroundColor Cyan
    Write-Host "  https://railway.app/dashboard" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ Deployment failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try manual deployment:" -ForegroundColor Yellow
    Write-Host "  https://railway.app/dashboard" -ForegroundColor Cyan
}

Write-Host ""
