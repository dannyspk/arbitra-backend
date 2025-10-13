# Test WebSocket Connection to Live Dashboard
Write-Host "🔍 Testing WebSocket Connection..." -ForegroundColor Cyan
Write-Host ""

# Check if backend is running
Write-Host "1️⃣ Checking if backend is running on port 8000..." -ForegroundColor Yellow
$connection = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue

if ($connection.TcpTestSucceeded) {
    Write-Host "   ✅ Backend is running on port 8000" -ForegroundColor Green
} else {
    Write-Host "   ❌ Backend is NOT running on port 8000" -ForegroundColor Red
    Write-Host "   Start it with: python -m uvicorn src.arbitrage.web:app --reload" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Check environment variable
Write-Host "2️⃣ Checking ARB_ALLOW_LIVE_ORDERS environment variable..." -ForegroundColor Yellow
$liveOrders = $env:ARB_ALLOW_LIVE_ORDERS
if ($liveOrders -eq "1") {
    Write-Host "   ✅ ARB_ALLOW_LIVE_ORDERS = 1" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  ARB_ALLOW_LIVE_ORDERS = $liveOrders (should be 1)" -ForegroundColor Yellow
    Write-Host "   The backend process needs to have this set to 1" -ForegroundColor Yellow
}
Write-Host ""

# Test HTTP endpoint
Write-Host "3️⃣ Testing HTTP API endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/dashboard?mode=live" -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ HTTP API is responding" -ForegroundColor Green
    }
} catch {
    Write-Host "   ❌ HTTP API error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Check Binance API keys
Write-Host "4️⃣ Checking Binance API credentials..." -ForegroundColor Yellow
if (Test-Path ".env") {
    $envContent = Get-Content .env -Raw
    if ($envContent -match 'BINANCE_API_KEY=(\S+)') {
        $keyPreview = $matches[1].Substring(0, [Math]::Min(10, $matches[1].Length)) + "..."
        Write-Host "   ✅ BINANCE_API_KEY found: $keyPreview" -ForegroundColor Green
    } else {
        Write-Host "   ❌ BINANCE_API_KEY not found in .env" -ForegroundColor Red
    }
    
    if ($envContent -match 'BINANCE_API_SECRET=(\S+)') {
        Write-Host "   ✅ BINANCE_API_SECRET found" -ForegroundColor Green
    } else {
        Write-Host "   ❌ BINANCE_API_SECRET not found in .env" -ForegroundColor Red
    }
}
Write-Host ""

Write-Host "=" * 80 -ForegroundColor Gray
Write-Host "📋 TESTING INSTRUCTIONS:" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test if WebSocket is working:" -ForegroundColor White
Write-Host "1. Open your browser to http://localhost:3000/trading" -ForegroundColor White
Write-Host "2. Click the Test/Live Mode toggle to switch to LIVE MODE" -ForegroundColor White
Write-Host "3. Open browser console (F12)" -ForegroundColor White
Write-Host "4. Look for these messages:" -ForegroundColor White
Write-Host "   [WS] Connecting to: ws://127.0.0.1:8000/ws/live-dashboard" -ForegroundColor Cyan
Write-Host "   [WS] ✅ Connected to live dashboard WebSocket" -ForegroundColor Green
Write-Host "   [WS] Connected: Connected to Binance WebSocket" -ForegroundColor Green
Write-Host ""
Write-Host "5. Check the dashboard - you should see:" -ForegroundColor White
Write-Host "   • Green banner: 'WebSocket Connected - Real-time updates active'" -ForegroundColor Green
Write-Host "   • Your live Binance balance" -ForegroundColor White
Write-Host "   • Any open Binance Futures positions" -ForegroundColor White
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Gray
