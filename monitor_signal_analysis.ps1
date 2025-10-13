#!/usr/bin/env pwsh
# Enhanced signal monitoring with SHORT vs LONG analysis

Write-Host "`n=== Live Signal Analysis & Monitoring ===" -ForegroundColor Cyan
Write-Host "Tracking signal patterns to optimize strategy logic`n" -ForegroundColor Gray

$backend = "http://127.0.0.1:8000"
$lastSignalCount = 0

function Get-SignalStats {
    try {
        $dashboard = Invoke-RestMethod -Uri "$backend/api/dashboard" -ErrorAction Stop
        
        # Count signal types
        $shorts = @($dashboard.signals | Where-Object { $_.action -eq 'open_short' })
        $longs = @($dashboard.signals | Where-Object { $_.action -eq 'open_long' })
        
        # Count completed trades
        $trades = @($dashboard.trades)
        $shortTrades = @($trades | Where-Object { $_.side -eq 'short' })
        $longTrades = @($trades | Where-Object { $_.side -eq 'long' })
        
        $shortWinning = @($shortTrades | Where-Object { $_.pnl -gt 0 })
        $longWinning = @($longTrades | Where-Object { $_.pnl -gt 0 })
        
        return @{
            Dashboard = $dashboard
            ShortSignals = $shorts.Count
            LongSignals = $longs.Count
            ShortTrades = $shortTrades.Count
            LongTrades = $longTrades.Count
            ShortWins = $shortWinning.Count
            LongWins = $longWinning.Count
            TotalSignals = $dashboard.signals.Count
        }
    } catch {
        Write-Host "  Error fetching data: $_" -ForegroundColor Red
        return $null
    }
}

function Show-SignalBreakdown {
    param($Stats)
    
    Write-Host "`n┌─────────────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "│          SIGNAL TYPE BREAKDOWN                  │" -ForegroundColor Cyan
    Write-Host "└─────────────────────────────────────────────────┘" -ForegroundColor Cyan
    
    Write-Host "`n  📈 LONG Signals (Buy the dip):" -ForegroundColor Green
    Write-Host "     Total: $($Stats.LongSignals)" -ForegroundColor White
    if ($Stats.LongTrades -gt 0) {
        $longWinRate = [math]::Round(($Stats.LongWins / $Stats.LongTrades) * 100, 1)
        Write-Host "     Completed Trades: $($Stats.LongTrades)" -ForegroundColor White
        Write-Host "     Win Rate: $longWinRate% ($($Stats.LongWins)/$($Stats.LongTrades))" -ForegroundColor $(if ($longWinRate -ge 60) { "Green" } else { "Yellow" })
    } else {
        Write-Host "     No completed trades yet" -ForegroundColor Gray
    }
    
    Write-Host "`n  📉 SHORT Signals (Fade the pump):" -ForegroundColor Red
    Write-Host "     Total: $($Stats.ShortSignals)" -ForegroundColor White
    if ($Stats.ShortTrades -gt 0) {
        $shortWinRate = [math]::Round(($Stats.ShortWins / $Stats.ShortTrades) * 100, 1)
        Write-Host "     Completed Trades: $($Stats.ShortTrades)" -ForegroundColor White
        Write-Host "     Win Rate: $shortWinRate% ($($Stats.ShortWins)/$($Stats.ShortTrades))" -ForegroundColor $(if ($shortWinRate -ge 60) { "Green" } else { "Yellow" })
    } else {
        Write-Host "     No completed trades yet" -ForegroundColor Gray
    }
    
    Write-Host ""
}

function Show-RecentSignals {
    param($Dashboard)
    
    if ($Dashboard.signals -and $Dashboard.signals.Count -gt 0) {
        Write-Host "┌─────────────────────────────────────────────────┐" -ForegroundColor Cyan
        Write-Host "│          RECENT SIGNALS (Last 10)               │" -ForegroundColor Cyan
        Write-Host "└─────────────────────────────────────────────────┘" -ForegroundColor Cyan
        Write-Host ""
        
        $recentSignals = $Dashboard.signals | Select-Object -First 10
        foreach ($sig in $recentSignals) {
            $time = [DateTimeOffset]::FromUnixTimeMilliseconds($sig.timestamp).LocalDateTime.ToString("HH:mm:ss")
            $color = if ($sig.action -eq 'open_long') { "Green" } elseif ($sig.action -eq 'open_short') { "Red" } else { "Yellow" }
            $arrow = if ($sig.action -eq 'open_long') { "↗" } elseif ($sig.action -eq 'open_short') { "↘" } else { "⟷" }
            
            Write-Host "  [$time] " -NoNewline -ForegroundColor Gray
            Write-Host "$arrow $($sig.symbol) " -NoNewline -ForegroundColor $color
            Write-Host "$($sig.action.ToUpper())" -NoNewline -ForegroundColor $color
            Write-Host " @ `$$($sig.price)" -ForegroundColor White
            
            # Show reason
            if ($sig.reason) {
                $reasonShort = $sig.reason.Substring(0, [Math]::Min(60, $sig.reason.Length))
                Write-Host "     Reason: $reasonShort..." -ForegroundColor DarkGray
            }
            
            $statusColor = if ($sig.status -eq 'executed') { 'Green' } elseif ($sig.status -eq 'failed') { 'Red' } else { 'Yellow' }
            Write-Host "     Status: $($sig.status)" -ForegroundColor $statusColor
            Write-Host ""
        }
    } else {
        Write-Host "`n  ⏳ No signals yet - waiting for market conditions..." -ForegroundColor Yellow
        Write-Host "     Strategies are running and monitoring every 15 seconds`n" -ForegroundColor Gray
    }
}

function Show-OpenPositions {
    param($Dashboard)
    
    if ($Dashboard.positions -and $Dashboard.positions.Count -gt 0) {
        Write-Host "┌─────────────────────────────────────────────────┐" -ForegroundColor Cyan
        Write-Host "│          OPEN POSITIONS                         │" -ForegroundColor Cyan
        Write-Host "└─────────────────────────────────────────────────┘" -ForegroundColor Cyan
        Write-Host ""
        
        foreach ($pos in $Dashboard.positions) {
            $sideColor = if ($pos.side -eq 'long') { 'Green' } else { 'Red' }
            $pnlColor = if ($pos.unrealized_pnl -gt 0) { 'Green' } else { 'Red' }
            
            Write-Host "  $($pos.symbol) " -NoNewline -ForegroundColor White
            Write-Host "$($pos.side.ToUpper())" -NoNewline -ForegroundColor $sideColor
            Write-Host " | Entry: `$$($pos.entry_price)" -NoNewline -ForegroundColor Gray
            Write-Host " | P&L: `$$($pos.unrealized_pnl) " -NoNewline -ForegroundColor $pnlColor
            Write-Host "($($pos.unrealized_pnl_pct)%)" -ForegroundColor $pnlColor
        }
        Write-Host ""
    }
}

# Main monitoring loop
Write-Host "Starting continuous monitoring (Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host "Updates every 10 seconds`n" -ForegroundColor Gray

$iteration = 0
while ($true) {
    $iteration++
    
    Clear-Host
    Write-Host "`n=== Live Signal Analysis & Monitoring ===" -ForegroundColor Cyan
    Write-Host "Update #$iteration | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
    Write-Host "─────────────────────────────────────────────────────────" -ForegroundColor DarkGray
    
    $stats = Get-SignalStats
    
    if ($stats) {
        # Check for new signals
        if ($stats.TotalSignals -gt $lastSignalCount) {
            [Console]::Beep(800, 200)
            [Console]::Beep(1000, 200)
            Write-Host "`n🔔 NEW SIGNAL DETECTED! 🔔`n" -ForegroundColor Yellow -BackgroundColor DarkRed
            $lastSignalCount = $stats.TotalSignals
        }
        
        Show-SignalBreakdown -Stats $stats
        Show-RecentSignals -Dashboard $stats.Dashboard
        Show-OpenPositions -Dashboard $stats.Dashboard
        
        # Analysis hints
        if ($stats.TotalSignals -eq 0) {
            Write-Host "┌─────────────────────────────────────────────────┐" -ForegroundColor Yellow
            Write-Host "│  💡 WAITING FOR FIRST SIGNAL                    │" -ForegroundColor Yellow
            Write-Host "└─────────────────────────────────────────────────┘" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "  Bear strategies need:" -ForegroundColor White
            Write-Host "    • LONG: -5%, -10%, or -12% drops" -ForegroundColor Green
            Write-Host "    • SHORT: +5% pump in 15 minutes" -ForegroundColor Red
            Write-Host ""
        } elseif ($stats.ShortTrades -ge 3 -and $stats.LongTrades -ge 3) {
            Write-Host "┌─────────────────────────────────────────────────┐" -ForegroundColor Green
            Write-Host "│  📊 ENOUGH DATA FOR ANALYSIS                    │" -ForegroundColor Green
            Write-Host "└─────────────────────────────────────────────────┘" -ForegroundColor Green
            Write-Host ""
            Write-Host "  Ready to compare SHORT vs LONG performance!" -ForegroundColor White
            Write-Host "  Check win rates above to optimize strategy logic." -ForegroundColor Gray
            Write-Host ""
        }
    }
    
    Write-Host "Press Ctrl+C to stop monitoring" -ForegroundColor DarkGray
    Start-Sleep -Seconds 10
}
