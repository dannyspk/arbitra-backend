# Simple WebSocket Connection Test
Write-Host "Testing WebSocket Connection..." -ForegroundColor Cyan
Write-Host ""

# 1. Check backend
Write-Host "1. Backend Server:" -ForegroundColor Yellow
try {
    $test = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue
    if ($test.TcpTestSucceeded) {
        Write-Host "   ✅ Running on port 8000" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Not running" -ForegroundColor Red
    }
} catch {
    Write-Host "   ❌ Error checking backend" -ForegroundColor Red
}

# 2. Check env var
Write-Host ""
Write-Host "2. Environment Variable:" -ForegroundColor Yellow
if ($env:ARB_ALLOW_LIVE_ORDERS -eq "1") {
    Write-Host "   ✅ ARB_ALLOW_LIVE_ORDERS = 1" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  ARB_ALLOW_LIVE_ORDERS = $($env:ARB_ALLOW_LIVE_ORDERS)" -ForegroundColor Yellow
}

# 3. Check API
Write-Host ""
Write-Host "3. HTTP API:" -ForegroundColor Yellow
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/dashboard?mode=live" -TimeoutSec 5
    Write-Host "   ✅ API responding" -ForegroundColor Green
} catch {
    Write-Host "   ❌ API error" -ForegroundColor Red
}

Write-Host ""
Write-Host "=" * 70
Write-Host "Next: Open browser console (F12) and check for:" -ForegroundColor Cyan
Write-Host "[WS] Connected to live dashboard WebSocket" -ForegroundColor Green
Write-Host "=" * 70
