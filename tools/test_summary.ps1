# Test script for liquidations summary
# Posts sample liquidation events to the running server and fetches the summary + debug endpoints
# Usage: Start the server (uvicorn arbitrage.web:app --reload --host 0.0.0.0 --port 8000)
# Then run in PowerShell: .\tools\test_summary.ps1

$base = 'http://localhost:8000'

function Send-Event([string]$sym, [string]$side, [double]$qty, [double]$price) {
    $ts = (Get-Date).ToUniversalTime().ToString("o")
    # Build JSON as a here-string so we control key casing (PowerShell hash tables are case-insensitive)
    $payload = @"
{
  "ts": "$ts",
  "msg": {
    "e": "forceOrder",
    "o": {
      "s": "$sym",
      "S": "$side",
      "q": $qty,
      "ap": $price,
      "z": $qty
    }
  }
}
"@

    try {
        Invoke-RestMethod -Uri "$base/liquidations/ingest" -Method POST -Body $payload -ContentType 'application/json' -ErrorAction Stop | Out-Null
        Write-Host "Posted $sym $side $qty@$price"
    } catch {
        $err = $_.Exception.Message -replace "`r`n", ' '
        Write-Warning ("Failed posting {0}: {1}" -f $sym, $err)
    }
}

# Post a few sample events to generate both long (SELL) and short (BUY) liquidations
Send-Event 'SOLUSDT' 'SELL' 5 23.45
Send-Event 'SOLUSDT' 'SELL' 2 23.50
Send-Event 'ETHUSDT' 'BUY' 0.4 1700
Send-Event 'BTCUSDT' 'SELL' 0.01 54000
Send-Event 'ADAUSDT' 'BUY' 100 0.33
Send-Event 'AVAXUSDT' 'SELL' 10 12.5

Start-Sleep -Seconds 1

# Fetch summary
try {
    Write-Host "\n=== /api/liquidations/summary ==="
    $s = Invoke-RestMethod -Uri "$base/api/liquidations/summary?minutes=10&min_qty=0" -Method GET -ErrorAction Stop
    $s | ConvertTo-Json -Depth 8 | Write-Output
} catch {
    Write-Warning "Failed to fetch summary: $_"
}

# Fetch debug
try {
    Write-Host "\n=== /debug/hotcoins_agg ==="
    $d = Invoke-RestMethod -Uri "$base/debug/hotcoins_agg" -Method GET -ErrorAction Stop
    $d | ConvertTo-Json -Depth 8 | Write-Output
} catch {
    Write-Warning "Failed to fetch debug endpoint: $_"
}

Write-Host "\nDone. If results are empty, ensure the server is running and the ingest endpoint is enabled."
