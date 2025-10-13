# Check COAIUSDT recent price movements to see why no signal

Write-Host "`n=== COAIUSDT Price Movement Analysis ===" -ForegroundColor Cyan
Write-Host ""

try {
    # Fetch recent klines from Binance FUTURES (last 60 minutes of 1-minute candles)
    $symbol = "COAIUSDT"
    $interval = "1m"
    $limit = 60
    
    Write-Host "Fetching last 60 minutes of price data from Binance Futures..." -ForegroundColor Yellow
    $url = "https://fapi.binance.com/fapi/v1/klines?symbol=$symbol&interval=$interval&limit=$limit"
    $klines = Invoke-RestMethod -Uri $url
    
    if ($klines -and $klines.Count -gt 0) {
        Write-Host "  Success! Received $($klines.Count) candles" -ForegroundColor Green
        Write-Host ""
        
        # Parse kline data
        $prices = @()
        foreach ($k in $klines) {
            $timestamp = [DateTimeOffset]::FromUnixTimeMilliseconds($k[0]).LocalDateTime
            $open = [double]$k[1]
            $high = [double]$k[2]
            $low = [double]$k[3]
            $close = [double]$k[4]
            
            $prices += [PSCustomObject]@{
                Time = $timestamp
                Open = $open
                High = $high
                Low = $low
                Close = $close
            }
        }
        
        # Get key price points
        $currentPrice = $prices[-1].Close
        $price15mAgo = if ($prices.Count -ge 15) { $prices[-15].Close } else { $prices[0].Close }
        $price30mAgo = if ($prices.Count -ge 30) { $prices[-30].Close } else { $prices[0].Close }
        $price60mAgo = $prices[0].Close
        
        Write-Host "=== KEY PRICE POINTS ===" -ForegroundColor Cyan
        Write-Host "  60 min ago: `$$([math]::Round($price60mAgo, 4))" -ForegroundColor White
        Write-Host "  30 min ago: `$$([math]::Round($price30mAgo, 4))" -ForegroundColor White
        Write-Host "  15 min ago: `$$([math]::Round($price15mAgo, 4))" -ForegroundColor White
        Write-Host "  Current:    `$$([math]::Round($currentPrice, 4))" -ForegroundColor White
        Write-Host ""
        
        # Calculate percentage changes
        $pct15 = (($currentPrice - $price15mAgo) / $price15mAgo) * 100
        $pct30 = (($currentPrice - $price30mAgo) / $price30mAgo) * 100
        $pct60 = (($currentPrice - $price60mAgo) / $price60mAgo) * 100
        
        Write-Host "=== PERCENTAGE CHANGES ===" -ForegroundColor Cyan
        Write-Host "  Last 15 min: $([math]::Round($pct15, 2))%" -ForegroundColor $(if ($pct15 -lt 0) { "Red" } else { "Green" })
        Write-Host "  Last 30 min: $([math]::Round($pct30, 2))%" -ForegroundColor $(if ($pct30 -lt 0) { "Red" } else { "Green" })
        Write-Host "  Last 60 min: $([math]::Round($pct60, 2))%" -ForegroundColor $(if ($pct60 -lt 0) { "Red" } else { "Green" })
        Write-Host ""
        
        # Check bear strategy conditions
        Write-Host "=== BEAR STRATEGY SIGNAL CONDITIONS ===" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Required for LONG entry (buy the dip):" -ForegroundColor Yellow
        
        Write-Host "  1. pct15 <= -5.0  : Current = $([math]::Round($pct15, 2)) " -NoNewline
        if ($pct15 -le -5.0) {
            Write-Host "PASS" -ForegroundColor Green
        } else {
            Write-Host "FAIL (needs $([math]::Round(-5.0 - $pct15, 2)) more drop)" -ForegroundColor Red
        }
        
        Write-Host "  2. pct30 <= -10.0 : Current = $([math]::Round($pct30, 2)) " -NoNewline
        if ($pct30 -le -10.0) {
            Write-Host "PASS" -ForegroundColor Green
        } else {
            Write-Host "FAIL (needs $([math]::Round(-10.0 - $pct30, 2)) more drop)" -ForegroundColor Red
        }
        
        Write-Host "  3. pct60 <= -12.0 : Current = $([math]::Round($pct60, 2)) " -NoNewline
        if ($pct60 -le -12.0) {
            Write-Host "PASS" -ForegroundColor Green
        } else {
            Write-Host "FAIL (needs $([math]::Round(-12.0 - $pct60, 2)) more drop)" -ForegroundColor Red
        }
        
        Write-Host ""
        Write-Host "Required for SHORT entry (fade the pump):" -ForegroundColor Yellow
        Write-Host "  1. pct15 >= +5.0  : Current = $([math]::Round($pct15, 2)) " -NoNewline
        if ($pct15 -ge 5.0) {
            Write-Host "PASS" -ForegroundColor Green
        } else {
            Write-Host "FAIL (needs $([math]::Round(5.0 - $pct15, 2)) more pump)" -ForegroundColor Red
        }
        
        Write-Host ""
        
        # Overall signal status
        $longCondition = ($pct15 -le -5.0) -and ($pct30 -le -10.0) -and ($pct60 -le -12.0)
        $shortCondition = ($pct15 -ge 5.0)
        
        Write-Host "=== SIGNAL STATUS ===" -ForegroundColor Cyan
        if ($longCondition) {
            Write-Host "  LONG SIGNAL SHOULD FIRE!" -ForegroundColor Green
            Write-Host "     Strategy should enter a LONG position to buy the dip" -ForegroundColor White
        } elseif ($shortCondition) {
            Write-Host "  SHORT SIGNAL SHOULD FIRE!" -ForegroundColor Green
            Write-Host "     Strategy should enter a SHORT position to fade the pump" -ForegroundColor White
        } else {
            Write-Host "  NO SIGNAL - Conditions not met" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "  Why?" -ForegroundColor Yellow
            if ($pct15 -gt -5.0 -and $pct15 -lt 5.0) {
                Write-Host "    - 15-min move ($([math]::Round($pct15, 2))) not extreme enough" -ForegroundColor Gray
                Write-Host "      (Needs either <= -5 or >= +5)" -ForegroundColor Gray
            }
            if ($pct30 -gt -10.0) {
                Write-Host "    - 30-min move ($([math]::Round($pct30, 2))) not strong enough for LONG" -ForegroundColor Gray
                Write-Host "      (Needs <= -10)" -ForegroundColor Gray
            }
            if ($pct60 -gt -12.0) {
                Write-Host "    - 60-min move ($([math]::Round($pct60, 2))) not strong enough for LONG" -ForegroundColor Gray
                Write-Host "      (Needs <= -12)" -ForegroundColor Gray
            }
            Write-Host ""
            Write-Host "  This suggests:" -ForegroundColor Cyan
            if ($pct60 -lt 0 -and $pct60 -gt -12.0) {
                Write-Host "    - Price IS falling, but GRADUALLY over time" -ForegroundColor White
                Write-Host "    - Not a sharp crash that triggers counter-trend entry" -ForegroundColor White
                Write-Host "    - Bear strategy designed for EXTREME moves only" -ForegroundColor White
            } else {
                Write-Host "    - Market relatively stable" -ForegroundColor White
                Write-Host "    - No extreme moves detected" -ForegroundColor White
            }
        }
        
        Write-Host ""
        
        # Show recent 10 candles
        Write-Host "=== RECENT 10 CANDLES ===" -ForegroundColor Cyan
        foreach ($p in $prices[-10..-1]) {
            $change = (($p.Close - $p.Open) / $p.Open) * 100
            $timeStr = $p.Time.ToString("HH:mm")
            $color = if ($change -lt 0) { "Red" } else { "Green" }
            $changeStr = [math]::Round($change, 2)
            Write-Host "  [$timeStr] $([math]::Round($p.Close, 4)) ($changeStr)" -ForegroundColor $color
        }
        
    } else {
        Write-Host "  No data received from Binance" -ForegroundColor Red
    }
    
} catch {
    Write-Host "  ERROR: $_" -ForegroundColor Red
    $errorMsg = $_.Exception.Message
    Write-Host "  Stack: $errorMsg" -ForegroundColor Gray
}

Write-Host ""
