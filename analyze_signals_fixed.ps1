#!/usr/bin/env pwsh
# Quick signal analysis - SHORT vs LONG performance

Write-Host "`n=== Signal Analysis Dashboard ===" -ForegroundColor Cyan
Write-Host "Analyzing SHORT vs LONG signal performance`n" -ForegroundColor Gray

$backend = "http://127.0.0.1:8000"

try {
    $dashboard = Invoke-RestMethod -Uri "$backend/api/dashboard" -ErrorAction Stop
    
    # Analyze signals
    $allSignals = @($dashboard.signals)
    $shorts = @($allSignals | Where-Object { $_.action -eq 'open_short' })
    $longs = @($allSignals | Where-Object { $_.action -eq 'open_long' })
    
    # Analyze trades
    $allTrades = @($dashboard.trades)
    $shortTrades = @($allTrades | Where-Object { $_.side -eq 'short' })
    $longTrades = @($allTrades | Where-Object { $_.side -eq 'long' })
    
    $shortWins = @($shortTrades | Where-Object { $_.pnl -gt 0 }).Count
    $longWins = @($longTrades | Where-Object { $_.pnl -gt 0 }).Count
    
    # Display results
    Write-Host "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—" -ForegroundColor Cyan
    Write-Host "â•‘       SIGNAL TYPE BREAKDOWN                    â•‘" -ForegroundColor Cyan
    Write-Host "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "  ðŸ“ˆ LONG Signals (Buy the dip):" -ForegroundColor Green
    Write-Host "     Total Signals: $($longs.Count)" -ForegroundColor White
    Write-Host "     Completed Trades: $($longTrades.Count)" -ForegroundColor White
    if ($longTrades.Count -gt 0) {
        $longWinRate = [math]::Round(($longWins / $longTrades.Count) * 100, 1)
        Write-Host "     Win Rate: $longWinRate% ($longWins/$($longTrades.Count))" -ForegroundColor $(if ($longWinRate -ge 60) { "Green" } else { "Yellow" })
        
        $longPnL = ($longTrades | Measure-Object -Property pnl -Sum).Sum
        $longPnLStr = [math]::Round($longPnL, 2)
        $longPnLColor = if ($longPnL -gt 0) { "Green" } else { "Red" }
        Write-Host "     Total P/L: `$$longPnLStr" -ForegroundColor $longPnLColor
    }
    
    Write-Host ""
    Write-Host "  ðŸ“‰ SHORT Signals (Fade the pump):" -ForegroundColor Red
    Write-Host "     Total Signals: $($shorts.Count)" -ForegroundColor White
    Write-Host "     Completed Trades: $($shortTrades.Count)" -ForegroundColor White
    if ($shortTrades.Count -gt 0) {
        $shortWinRate = [math]::Round(($shortWins / $shortTrades.Count) * 100, 1)
        Write-Host "     Win Rate: $shortWinRate% ($shortWins/$($shortTrades.Count))" -ForegroundColor $(if ($shortWinRate -ge 60) { "Green" } else { "Yellow" })
        
        $shortPnL = ($shortTrades | Measure-Object -Property pnl -Sum).Sum
        $shortPnLStr = [math]::Round($shortPnL, 2)
        $shortPnLColor = if ($shortPnL -gt 0) { "Green" } else { "Red" }
        Write-Host "     Total P/L: `$$shortPnLStr" -ForegroundColor $shortPnLColor
    }
    
    Write-Host ""
    Write-Host "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—" -ForegroundColor Cyan
    Write-Host "â•‘       RECENT SIGNALS                           â•‘" -ForegroundColor Cyan
    Write-Host "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•" -ForegroundColor Cyan
    Write-Host ""
    
    if ($allSignals.Count -gt 0) {
        $recent = $allSignals | Select-Object -First 10
        foreach ($sig in $recent) {
            $time = [DateTimeOffset]::FromUnixTimeMilliseconds($sig.timestamp).LocalDateTime.ToString("HH:mm:ss")
            $color = if ($sig.action -eq 'open_long') { "Green" } else { "Red" }
            $arrow = if ($sig.action -eq 'open_long') { "â†—" } else { "â†˜" }
            
            Write-Host "  [$time] $arrow $($sig.symbol) " -NoNewline -ForegroundColor $color
            Write-Host "$($sig.action.ToUpper()) @ `$$($sig.price)" -ForegroundColor White
            if ($sig.reason) {
                Write-Host "     $($sig.reason.Substring(0, [Math]::Min(70, $sig.reason.Length)))" -ForegroundColor DarkGray
            }
        }
    } else {
        Write-Host "  â³ No signals yet" -ForegroundColor Yellow
        Write-Host "     Waiting for market conditions..." -ForegroundColor Gray
        Write-Host ""
        Write-Host "  Bear strategy needs:" -ForegroundColor White
        Write-Host "    â€¢ LONG: -5%, -10%, or -12% drops" -ForegroundColor Green
        Write-Host "    â€¢ SHORT: +5% pump in 15 minutes" -ForegroundColor Red
    }
    
    Write-Host ""
    
    # Analysis recommendation
    if ($shortTrades.Count -ge 5 -and $longTrades.Count -ge 5) {
        Write-Host "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—" -ForegroundColor Green
        Write-Host "â•‘  âœ… SUFFICIENT DATA FOR ANALYSIS               â•‘" -ForegroundColor Green
        Write-Host "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Ready to optimize strategy logic!" -ForegroundColor White
        Write-Host "  Compare win rates and P and L above." -ForegroundColor Gray
        
        if ($shortWinRate -lt 50) {
            Write-Host ""
            Write-Host "  ðŸ’¡ SHORT win rate is low - consider adding:" -ForegroundColor Yellow
            Write-Host "     â€¢ Multi-timeframe confirmation (+5%, +8%, +10%)" -ForegroundColor White
            Write-Host "     â€¢ Increase threshold to +7% single timeframe" -ForegroundColor White
        }
        
        if ($longWinRate -lt 50) {
            Write-Host ""
            Write-Host "  ðŸ’¡ LONG win rate is low - consider:" -ForegroundColor Yellow
            Write-Host "     â€¢ Stricter entry filters" -ForegroundColor White
            Write-Host "     â€¢ Adjust stop-loss/take-profit levels" -ForegroundColor White
        }
    }
    
    Write-Host ""
    
} catch {
    $errorMsg = $_.ToString()
    Write-Host "  Error: $errorMsg" -ForegroundColor Red
}

