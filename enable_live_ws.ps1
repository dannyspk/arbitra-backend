# Enable Live Trading WebSocket for Dashboard
# This script enables the ARB_ALLOW_LIVE_ORDERS flag to allow WebSocket connections to show live positions

Write-Host "🔧 Enabling Live Trading WebSocket..." -ForegroundColor Cyan

# Set environment variable for current session
$env:ARB_ALLOW_LIVE_ORDERS = "1"

Write-Host "✅ ARB_ALLOW_LIVE_ORDERS has been set to 1" -ForegroundColor Green
Write-Host ""
Write-Host "⚠️  IMPORTANT:" -ForegroundColor Yellow
Write-Host "   This only affects the CURRENT PowerShell session." -ForegroundColor Yellow
Write-Host "   You need to restart your backend server for this to take effect." -ForegroundColor Yellow
Write-Host ""
Write-Host "📋 To make this permanent, add this to your .env file:" -ForegroundColor Cyan
Write-Host "   ARB_ALLOW_LIVE_ORDERS=1" -ForegroundColor White
Write-Host ""
Write-Host "🔄 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Stop your Python backend server (Ctrl+C)" -ForegroundColor White
Write-Host "   2. Run: python -m uvicorn src.arbitrage.web:app --reload" -ForegroundColor White
Write-Host "   3. The dashboard WebSocket will now show live Binance positions" -ForegroundColor White
Write-Host ""
