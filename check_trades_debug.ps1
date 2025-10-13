#!/usr/bin/env pwsh
# Debug trade recording issue

Write-Host "`n=== Trade Recording Diagnostic ===" -ForegroundColor Cyan
Write-Host ""

$railwayUrl = Read-Host "Enter Railway URL (or press Enter for localhost)"
if ([string]::IsNullOrWhiteSpace($railwayUrl)) {
    $railwayUrl = "http://127.0.0.1:8000"
}

try {
    Write-Host "Fetching dashboard from $railwayUrl..." -ForegroundColor Yellow
    $dash = Invoke-RestMethod "$railwayUrl/api/dashboard"
    
    Write-Host "`n--- STRATEGY STATUS ---" -ForegroundColor Cyan
    Write-Host "Running: $($dash.strategy.running)" -ForegroundColor White
    Write-Host "Symbol: $($dash.strategy.symbol)" -ForegroundColor White
    Write-Host "Mode: $($dash.strategy.mode)" -ForegroundColor White
    
    Write-Host "`n--- STATISTICS ---" -ForegroundColor Cyan
    Write-Host "Total Trades: $($dash.statistics.total_trades)" -ForegroundColor White
    Write-Host "Winning Trades: $($dash.statistics.winning_trades)" -ForegroundColor White
    Write-Host "Win Rate: $($dash.statistics.win_rate)%" -ForegroundColor White
    Write-Host "Realized P&L: `$$($dash.statistics.realized_pnl)" -ForegroundColor $(if ($dash.statistics.realized_pnl -gt 0) { "Green" } else { "Red" })
    
    Write-Host "`n--- SIGNALS ($($dash.signals.Count) total) ---" -ForegroundColor Cyan
    if ($dash.signals.Count -gt 0) {
        foreach ($sig in $dash.signals | Select-Object -First 5) {
            $time = [DateTimeOffset]::FromUnixTimeMilliseconds($sig.timestamp).LocalDateTime.ToString("HH:mm:ss")
            $color = if ($sig.action -like "*long*") { "Green" } else { "Red" }
            Write-Host "  [$time] $($sig.symbol) $($sig.action) @ `$$($sig.price) - $($sig.status)" -ForegroundColor $color
        }
    } else {
        Write-Host "  No signals" -ForegroundColor Gray
    }
    
    Write-Host "`n--- OPEN POSITIONS ($($dash.positions.Count) total) ---" -ForegroundColor Cyan
    if ($dash.positions.Count -gt 0) {
        foreach ($pos in $dash.positions) {
            $color = if ($pos.side -eq "long") { "Green" } else { "Red" }
            Write-Host "  $($pos.symbol) $($pos.side.ToUpper()) entry=`$$($pos.entry_price) P&L=`$$($pos.unrealized_pnl) ($($pos.unrealized_pnl_pct)%)" -ForegroundColor $color
        }
    } else {
        Write-Host "  No open positions" -ForegroundColor Gray
    }
    
    Write-Host "`n--- COMPLETED TRADES ($($dash.trades.Count) total) ---" -ForegroundColor Cyan
    if ($dash.trades.Count -gt 0) {
        Write-Host ""
        foreach ($trade in $dash.trades) {
            $time = [DateTimeOffset]::FromUnixTimeMilliseconds($trade.exit_time).LocalDateTime.ToString("HH:mm:ss")
            $color = if ($trade.pnl -gt 0) { "Green" } else { "Red" }
            Write-Host "  [$time] $($trade.symbol) $($trade.side.ToUpper())" -ForegroundColor White
            Write-Host "    Entry: `$$($trade.entry_price) | Exit: `$$($trade.exit_price)" -ForegroundColor Gray
            Write-Host "    P&L: `$$($trade.pnl) ($($trade.pnl_pct)%)" -ForegroundColor $color
            Write-Host "    Reason: $($trade.reason)" -ForegroundColor DarkGray
            Write-Host ""
        }
    } else {
        Write-Host "  ⚠️  NO TRADES RECORDED!" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Possible reasons:" -ForegroundColor White
        Write-Host "    1. Positions opened but not closed yet" -ForegroundColor Gray
        Write-Host "    2. Railway restarted (trades stored in memory)" -ForegroundColor Gray
        Write-Host "    3. Trade recording logic not triggering" -ForegroundColor Gray
        Write-Host ""
        
        if ($dash.signals.Count -gt 0) {
            $entrySignals = @($dash.signals | Where-Object { $_.action -like "open_*" })
            $exitSignals = @($dash.signals | Where-Object { $_.action -like "close_*" })
            
            Write-Host "  Signal Analysis:" -ForegroundColor Yellow
            Write-Host "    Entry signals (open_long/open_short): $($entrySignals.Count)" -ForegroundColor White
            Write-Host "    Exit signals (close_long/close_short): $($exitSignals.Count)" -ForegroundColor White
            
            if ($exitSignals.Count -eq 0) {
                Write-Host ""
                Write-Host "  💡 No exit signals detected!" -ForegroundColor Yellow
                Write-Host "     Positions may still be open or strategy hasn't hit TP/SL yet" -ForegroundColor Gray
            } elseif ($dash.statistics.total_trades -eq 0) {
                Write-Host ""
                Write-Host "  ⚠️  Exit signals exist but no trades recorded!" -ForegroundColor Red
                Write-Host "     This indicates a bug in close_position logic" -ForegroundColor Gray
                Write-Host "     Check Railway logs for error messages" -ForegroundColor Gray
            }
        }
    }
    
    Write-Host "`n--- DIAGNOSIS ---" -ForegroundColor Cyan
    if ($dash.trades.Count -gt 0) {
        Write-Host "✅ Trade recording is working!" -ForegroundColor Green
    } elseif ($dash.positions.Count -gt 0) {
        Write-Host "⏳ Positions are open but not closed yet" -ForegroundColor Yellow
        Write-Host "   Waiting for TP/SL to be hit..." -ForegroundColor Gray
    } elseif ($dash.signals.Count -gt 0) {
        $exitCount = @($dash.signals | Where-Object { $_.action -like "close_*" }).Count
        if ($exitCount -gt 0) {
            Write-Host "⚠️  Exit signals exist but no trades!" -ForegroundColor Yellow
            Write-Host "   Check Railway logs for debugging output" -ForegroundColor Gray
        } else {
            Write-Host "⏳ Only entry signals so far" -ForegroundColor Yellow
            Write-Host "   Positions haven't hit TP/SL yet" -ForegroundColor Gray
        }
    } else {
        Write-Host "⏳ No activity yet" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
    Write-Host "   Make sure Railway backend is running" -ForegroundColor Gray
}
