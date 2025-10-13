# Quick command to check strategy status

Write-Host "`n=== Live Strategy Status Check ===" -ForegroundColor Cyan
Write-Host ""

try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/live-strategy/status" -Method GET
    
    Write-Host "✅ Backend is responding!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Strategy Status:" -ForegroundColor Yellow
    Write-Host "  Running: " -NoNewline
    if ($status.running) {
        Write-Host "YES" -ForegroundColor Green
    } else {
        Write-Host "NO" -ForegroundColor Red
    }
    Write-Host "  Symbol: $($status.symbol)" -ForegroundColor White
    Write-Host "  Mode: $($status.mode)" -ForegroundColor White
    Write-Host ""
    
    if ($status.stats) {
        Write-Host "Trading Statistics:" -ForegroundColor Yellow
        Write-Host "  Total Trades: $($status.stats.total_trades)" -ForegroundColor White
        Write-Host "  Open Positions: $($status.stats.open_positions)" -ForegroundColor White
        Write-Host "  Win Rate: $($status.stats.win_rate)%" -ForegroundColor White
        Write-Host "  Realized PnL: $($status.stats.realized_pnl)" -ForegroundColor White
        Write-Host "  Unrealized PnL: $($status.stats.unrealized_pnl)" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "Tips:" -ForegroundColor Cyan
    if ($status.running) {
        Write-Host "  - Strategy is active and monitoring $($status.symbol)" -ForegroundColor Gray
        Write-Host "  - Check Trading page: http://localhost:3001/trading" -ForegroundColor Gray
        Write-Host "  - Signals appear when price deviates 1.2%+ from SMA" -ForegroundColor Gray
        if ($status.stats.total_trades -eq 0) {
            Write-Host "  - No trades yet = Market not meeting entry criteria (normal!)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  - Strategy is stopped. Start it from Trading page or via API" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "❌ Cannot connect to backend!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Is the backend running? Start it with:" -ForegroundColor Yellow
    Write-Host "  python -m uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor White
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
