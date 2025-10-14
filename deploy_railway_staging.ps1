# Deploy to Railway Staging
# This script sets up environment variables and deploys the backend

Write-Host "🚀 Railway Staging Deployment Script" -ForegroundColor Cyan
Write-Host "=" * 60

# Set environment variables for staging
Write-Host "`n📋 Setting environment variables..." -ForegroundColor Yellow

$envVars = @{
    "ENVIRONMENT" = "staging"
    "REQUIRE_AUTH" = "true"
    "REQUIRE_HTTPS" = "true"
    "ENABLE_RATE_LIMITING" = "true"
    "ENABLE_WEBSOCKET_AUTH" = "true"
    "JWT_ALGORITHM" = "HS256"
    "ACCESS_TOKEN_EXPIRE_MINUTES" = "60"
    "ENCRYPTION_KEY" = "b6q3t8Y11VkPm38OQA-CRDgpsqt7aIrA8MyyT6j9BK4="
    "DATABASE_PATH" = "data/staging/security.db"
    "LOG_LEVEL" = "INFO"
    "BINANCE_API_KEY" = "mCKNY0bBb5ZjWDRGwUpynLuGum6wHEOdCWKieqZSPUv8Q4qwiYgWlwWTtXZtXP23"
    "BINANCE_API_SECRET" = "9mt3IjYLzzpUtJvpBESJRp1vKLjItxrMbyC0vSk8NrVYqrjL75tBGe3kQjBTmcGB"
    "LUNARCRUSH_API_KEY" = "lgt3s7f4mwl8nqik0kxdrizj5amgetoygaibzs78"
    "ARB_MAX_POSITION_SIZE" = "100"
    "ARB_MAX_DAILY_TRADES" = "20"
    "ARB_MAX_LOSS_PERCENT" = "2"
    "ARB_ALLOW_LIVE_EXECUTION" = "1"
    "ARB_ALLOW_LIVE_ORDERS" = "1"
    "ALLOW_LIVE_ONCHAIN" = "0"
}

# Build the --set arguments
$setArgs = @()
foreach ($key in $envVars.Keys) {
    $setArgs += "--set"
    $setArgs += "$key=$($envVars[$key])"
}

Write-Host "   ✓ Prepared $($envVars.Count) environment variables" -ForegroundColor Green

# Note about JWT_SECRET_KEY
Write-Host "`n⚠️  IMPORTANT: You need to manually set JWT_SECRET_KEY in Railway dashboard" -ForegroundColor Yellow
Write-Host "   Generate a new secret key for staging (different from dev/prod)" -ForegroundColor Yellow

Write-Host "`n📝 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Go to Railway dashboard: https://railway.com/project/09bc8d71-6ef3-4dea-b211-3e72ce75b8e8"
Write-Host "2. Create a new service from GitHub repo (dannyspk/arbitra-backend)"
Write-Host "3. Select branch: development"
Write-Host "4. Add environment variables (see above)"
Write-Host "5. Add JWT_SECRET_KEY with a new random value"
Write-Host "6. Add CORS_ORIGINS for your staging domain"
Write-Host "7. Deploy!"

Write-Host "`n🔗 Automated Setup Option:" -ForegroundColor Cyan
Write-Host "If you prefer, I can guide you through using Railway CLI to:"
Write-Host "- Create a service from GitHub"
Write-Host "- Set all environment variables"
Write-Host "- Trigger deployment"

Write-Host "`n" + "=" * 60
Write-Host "✅ Deployment preparation complete!" -ForegroundColor Green
Write-Host "=" * 60
