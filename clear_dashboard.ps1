#!/usr/bin/env pwsh
# Clear Dashboard Data - Removes all test trades, positions, and signals

$backend = "http://127.0.0.1:8000"  # Change to Railway URL if needed

Write-Host "`n🗑️  Clear Dashboard Data" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host ""

Write-Host "⚠️  WARNING: This will clear ALL dashboard data:" -ForegroundColor Yellow
Write-Host "  • All signals" -ForegroundColor White
Write-Host "  • All trades (including trade history)" -ForegroundColor White
Write-Host "  • All open positions" -ForegroundColor White
Write-Host "  • All statistics" -ForegroundColor White
Write-Host ""

$confirm = Read-Host "Type 'YES' to confirm"

if ($confirm -ne "YES") {
    Write-Host "`n❌ Cancelled" -ForegroundColor Red
    exit 0
}

Write-Host "`nClearing dashboard data..." -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod -Uri "$backend/api/dashboard/clear" -Method POST -ErrorAction Stop
    
    if ($response.success) {
        Write-Host "✅ $($response.message)" -ForegroundColor Green
        Write-Host ""
        Write-Host "Dashboard has been reset. Refresh your browser to see the changes." -ForegroundColor Cyan
    } else {
        Write-Host "❌ Failed to clear dashboard" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    
    if ($_.ErrorDetails.Message) {
        $err = $_.ErrorDetails.Message | ConvertFrom-Json
        Write-Host "Detail: $($err.detail)" -ForegroundColor Red
    }
}

Write-Host ""
