# Real Trading Setup Script
# Run this to configure your environment for live trading

Write-Host "`n🚨 REAL TRADING SETUP" -ForegroundColor Red
Write-Host "=" * 60 -ForegroundColor Red
Write-Host "This will enable REAL MONEY trading. Proceed with caution!" -ForegroundColor Yellow
Write-Host ""

# Check if .env exists
$envFile = "C:\arbitrage\.env"
$envExists = Test-Path $envFile

Write-Host "Step 1: Check Environment File" -ForegroundColor Cyan
if ($envExists) {
    Write-Host "✅ .env file exists at $envFile" -ForegroundColor Green
} else {
    Write-Host "❌ .env file not found. Creating..." -ForegroundColor Yellow
    New-Item -Path $envFile -ItemType File -Force | Out-Null
    Write-Host "✅ Created .env file" -ForegroundColor Green
}

Write-Host "`nStep 2: Binance API Configuration" -ForegroundColor Cyan
Write-Host "You need to add these to your .env file:" -ForegroundColor Yellow
Write-Host ""
Write-Host "BINANCE_API_KEY=your_api_key_here" -ForegroundColor White
Write-Host "BINANCE_API_SECRET=your_secret_key_here" -ForegroundColor White
Write-Host ""
Write-Host "Get your API key from: https://www.binance.com/en/my/settings/api-management" -ForegroundColor Gray

$hasApiKey = Select-String -Path $envFile -Pattern "BINANCE_API_KEY" -Quiet
$hasApiSecret = Select-String -Path $envFile -Pattern "BINANCE_API_SECRET" -Quiet

if ($hasApiKey -and $hasApiSecret) {
    Write-Host "✅ API credentials found in .env" -ForegroundColor Green
} else {
    Write-Host "⚠️  API credentials NOT configured" -ForegroundColor Red
    Write-Host ""
    $configure = Read-Host "Do you want to configure API keys now? (y/n)"
    
    if ($configure -eq 'y') {
        $apiKey = Read-Host "Enter your Binance API Key"
        $apiSecret = Read-Host "Enter your Binance API Secret" -AsSecureString
        $apiSecretPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiSecret))
        
        Add-Content -Path $envFile -Value "`n# Binance API Credentials"
        Add-Content -Path $envFile -Value "BINANCE_API_KEY=$apiKey"
        Add-Content -Path $envFile -Value "BINANCE_API_SECRET=$apiSecretPlain"
        
        Write-Host "✅ API credentials saved to .env" -ForegroundColor Green
    }
}

Write-Host "`nStep 3: Risk Management Settings" -ForegroundColor Cyan

# Check for risk settings
$hasRiskSettings = Select-String -Path $envFile -Pattern "ARB_MAX_POSITION_SIZE" -Quiet

if (-not $hasRiskSettings) {
    Write-Host "Adding default risk management settings..." -ForegroundColor Yellow
    
    Add-Content -Path $envFile -Value "`n# Risk Management"
    Add-Content -Path $envFile -Value "ARB_MAX_POSITION_SIZE=10  # Start small: $10 USDT"
    Add-Content -Path $envFile -Value "ARB_MAX_DAILY_TRADES=5   # Only 5 trades per day"
    Add-Content -Path $envFile -Value "ARB_MAX_LOSS_PERCENT=1   # Max 1% loss"
    
    Write-Host "✅ Risk management settings added" -ForegroundColor Green
} else {
    Write-Host "✅ Risk management settings found" -ForegroundColor Green
}

Write-Host "`nStep 4: Live Execution Flag" -ForegroundColor Cyan
Write-Host "⚠️  WARNING: This enables REAL trading with REAL money!" -ForegroundColor Red

$liveEnabled = Select-String -Path $envFile -Pattern "ARB_ALLOW_LIVE_EXECUTION=1" -Quiet

if ($liveEnabled) {
    Write-Host "🔴 Live execution is ENABLED" -ForegroundColor Red
} else {
    Write-Host "✅ Live execution is DISABLED (safe mode)" -ForegroundColor Green
    Write-Host ""
    Write-Host "To enable live trading, add to .env:" -ForegroundColor Yellow
    Write-Host "ARB_ALLOW_LIVE_EXECUTION=1" -ForegroundColor White
    Write-Host ""
    $enable = Read-Host "Do you want to enable live trading now? (yes/no)"
    
    if ($enable -eq 'yes') {
        Add-Content -Path $envFile -Value "`n# Enable Live Trading"
        Add-Content -Path $envFile -Value "ARB_ALLOW_LIVE_EXECUTION=1"
        Write-Host "🔴 Live trading ENABLED!" -ForegroundColor Red
        Write-Host "⚠️  Remember: Start with small position sizes!" -ForegroundColor Yellow
    } else {
        Write-Host "✅ Staying in safe mode (paper trading only)" -ForegroundColor Green
    }

Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "Configuration Summary:" -ForegroundColor Cyan
Write-Host ""

# Display current settings
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile | Where-Object { $_ -notmatch '^#' -and $_ -notmatch '^\s*$' }
    foreach ($line in $envContent) {
        if ($line -match "API_SECRET") {
            Write-Host "BINANCE_API_SECRET=***HIDDEN***" -ForegroundColor Gray
        } else {
            Write-Host $line -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Review the settings in .env file" -ForegroundColor White
Write-Host "2. Read REAL_TRADING_SETUP_GUIDE.md thoroughly" -ForegroundColor White
Write-Host "3. Test in paper trading mode first (ARB_ALLOW_LIVE_EXECUTION=0)" -ForegroundColor White
Write-Host "4. Start with tiny position sizes ($10)" -ForegroundColor White
Write-Host "5. Monitor constantly when live trading" -ForegroundColor White
Write-Host ""
Write-Host "To start the backend with these settings:" -ForegroundColor Cyan
Write-Host "cd C:\arbitrage" -ForegroundColor White
Write-Host "python -m uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor White
Write-Host ""
Write-Host "🚨 TRADE SAFELY! NEVER RISK MORE THAN YOU CAN AFFORD TO LOSE! 🚨" -ForegroundColor Red
Write-Host ""
