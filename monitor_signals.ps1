# Real-time Strategy Signal Monitor
# Shows live updates when strategies generate signals

param(
    [int]$RefreshSeconds = 10,
    [switch]$ShowDebug
)

$backend = "http://127.0.0.1:8000"
$lastSignalCount = 0
$startTime = Get-Date

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        LIVE STRATEGY SIGNAL MONITOR                       ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

function Get-TimeElapsed {
    $elapsed = (Get-Date) - $startTime
    return "{0:D2}:{1:D2}:{2:D2}" -f $elapsed.Hours, $elapsed.Minutes, $elapsed.Seconds
}

function Show-StrategyStatus {
    try {
        $status = Invoke-RestMethod -Uri "$backend/api/live-strategy/status" -ErrorAction Stop
        
        Write-Host "`n┌─ Active Strategies ──────────────────────────────────────┐" -ForegroundColor Yellow
        if ($status.active_count -gt 0) {
            foreach ($s in $status.strategies) {
                $emoji = switch ($s.mode) {
                    'bear' { '🐻' }
                    'bull' { '🐂' }
                    'scalp' { '⚡' }
                    'range' { '📊' }
                    default { '📈' }
                }
                Write-Host "  $emoji $($s.symbol.PadRight(12)) $($s.mode.ToUpper().PadRight(8)) ($($s.interval))" -ForegroundColor White
            }
        } else {
            Write-Host "  No strategies running" -ForegroundColor Gray
        }
        Write-Host "└──────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
        
        return $true
    } catch {
        Write-Host "  ⚠️  Backend not responding" -ForegroundColor Red
        return $false
    }
}

function Show-Dashboard {
    try {
        $dashboard = Invoke-RestMethod -Uri "$backend/api/dashboard" -ErrorAction Stop
        
        # Signals
        Write-Host "`n┌─ Recent Signals ─────────────────────────────────────────┐" -ForegroundColor Cyan
        if ($dashboard.signals -and $dashboard.signals.Count -gt 0) {
            $script:lastSignalCount = $dashboard.signals.Count
            
            Write-Host "  📊 Total: $($dashboard.signals.Count) signals" -ForegroundColor Green
            Write-Host ""
            
            foreach ($sig in $dashboard.signals | Select-Object -First 5) {
                $time = [DateTimeOffset]::FromUnixTimeMilliseconds($sig.timestamp).LocalDateTime.ToString("HH:mm:ss")
                $price = if ($sig.price) { "$([math]::Round($sig.price, 2))" } else { "N/A" }
                
                $actionColor = if ($sig.action -like "*long*") { 'Green' } else { 'Red' }
                $statusEmoji = switch ($sig.status) {
                    'executed' { '✅' }
                    'pending' { '⏳' }
                    'failed' { '❌' }
                    default { '❓' }
                }
                
                Write-Host "  [$time] $statusEmoji $($sig.symbol)" -ForegroundColor White
                Write-Host "    └─ Action: " -NoNewline -ForegroundColor Gray
                Write-Host "$($sig.action)" -ForegroundColor $actionColor -NoNewline
                Write-Host " @ `$$price" -ForegroundColor White
                
                if ($ShowDebug) {
                    $reasonShort = if ($sig.reason.Length -gt 50) { 
                        $sig.reason.Substring(0, 47) + "..." 
                    } else { 
                        $sig.reason 
                    }
                    Write-Host "       Reason: $reasonShort" -ForegroundColor DarkGray
                }
                Write-Host ""
            }
        } else {
            Write-Host "  ⏳ Waiting for market conditions..." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "  💡 Strategies are monitoring:" -ForegroundColor Gray
            Write-Host "     • BTCUSDT Scalp: 1.2% SMA deviation needed" -ForegroundColor DarkGray
            Write-Host "     • AIAUSDT Bear: +5% pump or -5/-10/-12% dump" -ForegroundColor DarkGray
            Write-Host "     • COAIUSDT Bear: +5% pump or -5/-10/-12% dump" -ForegroundColor DarkGray
        }
        Write-Host "└──────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
        
        # Positions
        if ($dashboard.positions -and $dashboard.positions.Count -gt 0) {
            Write-Host "`n┌─ Open Positions ─────────────────────────────────────────┐" -ForegroundColor Green
            foreach ($pos in $dashboard.positions) {
                $pnlColor = if ($pos.unrealized_pnl -ge 0) { 'Green' } else { 'Red' }
                $sideEmoji = if ($pos.side -eq 'long') { '📈' } else { '📉' }
                
                Write-Host "  $sideEmoji $($pos.symbol) - $($pos.side.ToUpper())" -ForegroundColor White
                Write-Host "     Entry: `$$($pos.entry_price) | Size: $($pos.size)" -ForegroundColor Gray
                Write-Host "     P&L: " -NoNewline -ForegroundColor Gray
                Write-Host "`$$($pos.unrealized_pnl) ($($pos.unrealized_pnl_pct)%)" -ForegroundColor $pnlColor
                Write-Host ""
            }
            Write-Host "└──────────────────────────────────────────────────────────┘" -ForegroundColor Green
        }
        
        # Statistics
        if ($dashboard.statistics) {
            Write-Host "`n┌─ Statistics ─────────────────────────────────────────────┐" -ForegroundColor Magenta
            $stats = $dashboard.statistics
            
            $winRateColor = if ($stats.win_rate -ge 60) { 'Green' } 
                           elseif ($stats.win_rate -ge 40) { 'Yellow' } 
                           else { 'Red' }
            
            $pnlColor = if ($stats.total_pnl -ge 0) { 'Green' } else { 'Red' }
            
            Write-Host "  Trades: $($stats.total_trades) | Win Rate: " -NoNewline -ForegroundColor Gray
            Write-Host "$($stats.win_rate.ToString('F1'))%" -ForegroundColor $winRateColor
            Write-Host "  Realized P&L: " -NoNewline -ForegroundColor Gray
            Write-Host "`$$($stats.realized_pnl)" -ForegroundColor $pnlColor
            if ($stats.active_positions -gt 0) {
                Write-Host "  Active Positions: $($stats.active_positions)" -ForegroundColor Cyan
            }
            Write-Host "└──────────────────────────────────────────────────────────┘" -ForegroundColor Magenta
        }
        
        return $true
    } catch {
        Write-Host "  ⚠️  Could not fetch dashboard data" -ForegroundColor Red
        return $false
    }
}

# Main monitoring loop
Write-Host "Monitoring started at $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Green
Write-Host "Refresh interval: $RefreshSeconds seconds" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Gray

$iteration = 0

while ($true) {
    $iteration++
    
    # Clear screen every 10 iterations to keep it clean
    if ($iteration % 10 -eq 1) {
        Clear-Host
        Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
        Write-Host "║        LIVE STRATEGY SIGNAL MONITOR                       ║" -ForegroundColor Cyan
        Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    }
    
    Write-Host "`n" + ("═" * 60) -ForegroundColor DarkGray
    Write-Host "⏱️  Update #$iteration | Elapsed: $(Get-TimeElapsed) | $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor White
    Write-Host ("═" * 60) -ForegroundColor DarkGray
    
    $strategyOk = Show-StrategyStatus
    $dashboardOk = Show-Dashboard
    
    if (-not $strategyOk -or -not $dashboardOk) {
        Write-Host "`n⚠️  Backend connection issue - retrying in $RefreshSeconds seconds..." -ForegroundColor Yellow
    }
    
    # Check if new signals appeared
    try {
        $currentDashboard = Invoke-RestMethod -Uri "$backend/api/dashboard" -ErrorAction SilentlyContinue
        if ($currentDashboard.signals.Count -gt $lastSignalCount -and $lastSignalCount -gt 0) {
            Write-Host "`n🔔 NEW SIGNAL DETECTED!" -ForegroundColor Green -BackgroundColor Black
            [console]::beep(800, 200)
            Start-Sleep -Milliseconds 200
            [console]::beep(1000, 200)
        }
    } catch {}
    
    Write-Host "`n⏳ Next update in $RefreshSeconds seconds... (Ctrl+C to stop)" -ForegroundColor DarkGray
    
    Start-Sleep -Seconds $RefreshSeconds
}
