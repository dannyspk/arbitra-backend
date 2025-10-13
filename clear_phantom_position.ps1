#!/usr/bin/env pwsh
# Clear the phantom MYXUSDT position from dashboard

$backend = "http://127.0.0.1:8000"

Write-Host "`n🧹 Clearing Phantom MYXUSDT Position" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host ""

# Check current positions
Write-Host "1. Checking current positions..." -ForegroundColor Yellow
try {
    $dash = Invoke-RestMethod "$backend/api/dashboard" -ErrorAction Stop
    Write-Host "   Found $($dash.positions.Count) positions" -ForegroundColor Cyan
    
    if ($dash.positions) {
        foreach ($pos in $dash.positions) {
            Write-Host "   - $($pos.symbol) ($($pos.side))" -ForegroundColor White
        }
    }
} catch {
    Write-Host "   ❌ Failed to get dashboard: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Clear all dashboard data (positions, trades, signals)
Write-Host "2. Clearing dashboard data..." -ForegroundColor Yellow
try {
    $result = Invoke-RestMethod "$backend/api/dashboard/clear" -Method POST -ErrorAction Stop
    Write-Host "   ✅ Dashboard cleared!" -ForegroundColor Green
    Write-Host "   Cleared: $($result.cleared -join ', ')" -ForegroundColor Cyan
} catch {
    Write-Host "   ❌ Failed to clear: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Alternative: Restart the server to clear in-memory data" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Verify positions are cleared
Write-Host "3. Verifying positions cleared..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
try {
    $dash = Invoke-RestMethod "$backend/api/dashboard" -ErrorAction Stop
    if ($dash.positions.Count -eq 0) {
        Write-Host "   ✅ All positions cleared!" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Still have $($dash.positions.Count) positions" -ForegroundColor Yellow
        foreach ($pos in $dash.positions) {
            Write-Host "   - $($pos.symbol) ($($pos.side))" -ForegroundColor White
        }
    }
} catch {
    Write-Host "   ❌ Failed to verify: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host "Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "The WebSocket watcher should stop now." -ForegroundColor White
Write-Host "Check the terminal - it should no longer show MYXUSDT position messages" -ForegroundColor Gray
Write-Host ""
