# Script to copy Binance API keys from system environment variables to .env file

Write-Host "`n🔄 Copying Binance Keys from Environment Variables to .env" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Get keys from environment
Write-Host "Step 1: Reading environment variables..." -ForegroundColor Yellow
$apiKey = [System.Environment]::GetEnvironmentVariable("BINANCE_API_KEY", "User")
$apiSecret = [System.Environment]::GetEnvironmentVariable("BINANCE_API_SECRET", "User")

# If not in User, try Machine (System) variables
if (-not $apiKey) {
    $apiKey = [System.Environment]::GetEnvironmentVariable("BINANCE_API_KEY", "Machine")
}
if (-not $apiSecret) {
    $apiSecret = [System.Environment]::GetEnvironmentVariable("BINANCE_API_SECRET", "Machine")
}

# Also check current process environment
if (-not $apiKey) {
    $apiKey = $env:BINANCE_API_KEY
}
if (-not $apiSecret) {
    $apiSecret = $env:BINANCE_API_SECRET
}

# Display what we found
if ($apiKey) {
    Write-Host "✅ Found BINANCE_API_KEY: $apiKey" -ForegroundColor Green
} else {
    Write-Host "❌ BINANCE_API_KEY not found in environment" -ForegroundColor Red
}

if ($apiSecret) {
    $maskedSecret = $apiSecret.Substring(0, [Math]::Min(8, $apiSecret.Length)) + "..." + $apiSecret.Substring([Math]::Max(0, $apiSecret.Length - 4))
    Write-Host "✅ Found BINANCE_API_SECRET: $maskedSecret" -ForegroundColor Green
} else {
    Write-Host "❌ BINANCE_API_SECRET not found in environment" -ForegroundColor Red
}

Write-Host ""

if (-not $apiKey -or -not $apiSecret) {
    Write-Host "⚠️  ERROR: One or both API keys not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To view all environment variables with 'BINANCE' in the name:" -ForegroundColor Yellow
    Write-Host "Get-ChildItem Env: | Where-Object { `$_.Name -like '*BINANCE*' }" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Check/create .env file
Write-Host "Step 2: Preparing .env file..." -ForegroundColor Yellow
$envFile = "C:\arbitrage\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "Creating new .env file..." -ForegroundColor Gray
    New-Item -Path $envFile -ItemType File -Force | Out-Null
}

# Read existing .env content
$envContent = @()
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile
}

# Remove any existing Binance key lines
Write-Host "Removing old Binance key entries (if any)..." -ForegroundColor Gray
$envContent = $envContent | Where-Object { 
    $_ -notmatch "^BINANCE_API_KEY=" -and 
    $_ -notmatch "^BINANCE_API_SECRET=" 
}

# Add new keys
Write-Host "Adding Binance API credentials..." -ForegroundColor Gray
$newContent = @()
$newContent += $envContent
$newContent += ""
$newContent += "# Binance API Credentials (copied from environment variables)"
$newContent += "BINANCE_API_KEY=$apiKey"
$newContent += "BINANCE_API_SECRET=$apiSecret"

# Write to file
$newContent | Set-Content $envFile

Write-Host "✅ API keys written to .env file" -ForegroundColor Green
Write-Host ""

# Add risk management if not present
Write-Host "Step 3: Checking risk management settings..." -ForegroundColor Yellow
$hasRiskSettings = $envContent | Where-Object { $_ -match "ARB_MAX_POSITION_SIZE" }

if (-not $hasRiskSettings) {
    Write-Host "Adding default risk management settings..." -ForegroundColor Gray
    Add-Content -Path $envFile -Value ""
    Add-Content -Path $envFile -Value "# Risk Management Settings"
    Add-Content -Path $envFile -Value "ARB_MAX_POSITION_SIZE=10  # Start small: `$10 USDT"
    Add-Content -Path $envFile -Value "ARB_MAX_DAILY_TRADES=5   # Only 5 trades per day"
    Add-Content -Path $envFile -Value "ARB_MAX_LOSS_PERCENT=1   # Max 1% loss"
    Add-Content -Path $envFile -Value "ARB_ALLOW_LIVE_EXECUTION=0  # Paper trading mode (SAFE)"
    Write-Host "✅ Risk management settings added" -ForegroundColor Green
} else {
    Write-Host "✅ Risk management settings already exist" -ForegroundColor Green
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "✅ SUCCESS! Configuration complete" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Test API connection: python test_binance_api.py" -ForegroundColor White
Write-Host "2. Review settings: Get-Content .env" -ForegroundColor White
Write-Host "3. Start backend: python -m uvicorn src.arbitrage.web:app --reload" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  NOTE: Live trading is DISABLED by default (ARB_ALLOW_LIVE_EXECUTION=0)" -ForegroundColor Yellow
Write-Host "    Test in paper mode for 24-48 hours before enabling live trading!" -ForegroundColor Yellow
Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
