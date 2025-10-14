# Environment Switcher for Windows PowerShell
# Usage: .\switch_env.ps1 development|testing|production

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('development', 'testing', 'production')]
    [string]$Environment
)

$envFile = ".env.$Environment"

if (!(Test-Path $envFile)) {
    Write-Host "❌ Error: $envFile not found!" -ForegroundColor Red
    exit 1
}

Write-Host "`n🔄 Switching to $Environment environment..." -ForegroundColor Cyan

# Backup current .env if it exists
if (Test-Path ".env") {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backup = ".env.backup.$timestamp"
    Copy-Item ".env" $backup
    Write-Host "📦 Backed up current .env to $backup" -ForegroundColor Yellow
}

# Copy environment-specific file to .env
Copy-Item $envFile ".env" -Force
Write-Host "✅ Switched to $Environment environment" -ForegroundColor Green

# Display current configuration
Write-Host "`n📋 Current Configuration:" -ForegroundColor Cyan
Get-Content ".env" | Select-String "^ENVIRONMENT=|^REQUIRE_AUTH=|^REQUIRE_HTTPS=|^ENABLE_RATE_LIMITING="

# Create necessary directories
Write-Host "`n📁 Creating directory structure..." -ForegroundColor Cyan
$dirs = @(
    "data/dev",
    "data/test", 
    "data/staging",
    "data/prod"
)

foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "   Created: $dir" -ForegroundColor Gray
    }
}

# Warning for production
if ($Environment -eq "production") {
    Write-Host "`n⚠️  WARNING: PRODUCTION MODE" -ForegroundColor Red
    Write-Host "   - Security features are ENFORCED" -ForegroundColor Yellow
    Write-Host "   - Update JWT_SECRET_KEY before deploying" -ForegroundColor Yellow
    Write-Host "   - Update ENCRYPTION_KEY before deploying" -ForegroundColor Yellow
    Write-Host "   - Configure proper CORS_ORIGINS" -ForegroundColor Yellow
    Write-Host "   - Remove default Binance API keys" -ForegroundColor Yellow
}

Write-Host "`n[OK] Environment switch complete!`n" -ForegroundColor Green
