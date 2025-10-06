# Test DeFi Vault Monitoring APIs
# Run this after the server is up to test the monitoring system

Write-Host "Testing DeFi Vault Monitoring System" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""

# Wait for server to be ready
Start-Sleep -Seconds 3

# 1. Get current vaults
Write-Host "1. Fetching current vaults..." -ForegroundColor Cyan
$vaults = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/defi-vaults'
$firstVault = $vaults.vaults[0]
Write-Host "   Found $($vaults.total_vaults) vaults" -ForegroundColor Yellow
Write-Host "   First vault: $($firstVault.name) - $($firstVault.apy)% APY" -ForegroundColor Yellow
$poolId = $firstVault.id
Write-Host ""

# 2. Check APY history (should be empty initially)
Write-Host "2. Checking APY history for $poolId..." -ForegroundColor Cyan
try {
    $history = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/defi-vaults/history/$poolId"
    Write-Host "   Data points: $($history.data_points)" -ForegroundColor Yellow
    Write-Host "   Current APY: $($history.current_apy)%" -ForegroundColor Yellow
} catch {
    Write-Host "   No history yet (monitor will populate in ~5 minutes)" -ForegroundColor Gray
}
Write-Host ""

# 3. Create an alert for APY drop
Write-Host "3. Creating APY drop alert..." -ForegroundColor Cyan
$alertBody = @{
    pool_id = $poolId
    alert_type = "apy_drop"
    threshold = 20.0
    notification_method = "webhook"
    webhook_url = "https://webhook.site/your-unique-id"  # Replace with your test webhook
} | ConvertTo-Json

try {
    $alertResponse = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/defi-vaults/alerts' `
        -ContentType 'application/json' `
        -Body $alertBody
    Write-Host "   Alert created! ID: $($alertResponse.alert_id)" -ForegroundColor Green
    Write-Host "   Will trigger if APY drops by 20% or more" -ForegroundColor Yellow
    $alertId = $alertResponse.alert_id
} catch {
    Write-Host "   Error creating alert: $_" -ForegroundColor Red
}
Write-Host ""

# 4. Create a high APY alert
Write-Host "4. Creating high APY alert..." -ForegroundColor Cyan
$alertBody2 = @{
    pool_id = $poolId
    alert_type = "apy_above"
    threshold = 25.0
    notification_method = "webhook"
    webhook_url = "https://webhook.site/your-unique-id"
} | ConvertTo-Json

try {
    $alertResponse2 = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/defi-vaults/alerts' `
        -ContentType 'application/json' `
        -Body $alertBody2
    Write-Host "   Alert created! ID: $($alertResponse2.alert_id)" -ForegroundColor Green
    Write-Host "   Will trigger if APY goes above 25%" -ForegroundColor Yellow
} catch {
    Write-Host "   Error creating alert: $_" -ForegroundColor Red
}
Write-Host ""

# 5. List all alerts
Write-Host "5. Listing all alerts..." -ForegroundColor Cyan
try {
    $alerts = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/defi-vaults/alerts'
    Write-Host "   Total active alerts: $($alerts.total_alerts)" -ForegroundColor Yellow
    foreach ($alert in $alerts.alerts) {
        Write-Host "   - [$($alert.alert_type)] $($alert.pool_id) @ $($alert.threshold)%" -ForegroundColor Gray
    }
} catch {
    Write-Host "   Error fetching alerts: $_" -ForegroundColor Red
}
Write-Host ""

# 6. Track a position
Write-Host "6. Tracking a user position..." -ForegroundColor Cyan
$positionBody = @{
    user_id = "0xTestWallet123"
    pool_id = $poolId
    amount = 10000
    entry_apy = $firstVault.apy
} | ConvertTo-Json

try {
    $posResponse = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/defi-vaults/positions' `
        -ContentType 'application/json' `
        -Body $positionBody
    Write-Host "   Position tracked! Entry APY: $($posResponse.position.entry_apy)%" -ForegroundColor Green
} catch {
    Write-Host "   Error tracking position: $_" -ForegroundColor Red
}
Write-Host ""

# 7. Get user positions
Write-Host "7. Fetching user positions..." -ForegroundColor Cyan
try {
    $positions = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/defi-vaults/positions/0xTestWallet123'
    Write-Host "   Total positions: $($positions.total_positions)" -ForegroundColor Yellow
    foreach ($pos in $positions.positions) {
        $deltaColor = if ($pos.apy_delta -lt 0) { "Red" } else { "Green" }
        Write-Host "   - Amount: `$$($pos.amount) | Entry: $($pos.entry_apy)% | Current: $($pos.current_apy)% | Delta: $($pos.apy_delta_pct)%" -ForegroundColor $deltaColor
    }
} catch {
    Write-Host "   Error fetching positions: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "=====================================" -ForegroundColor Green
Write-Host "Test complete!" -ForegroundColor Green
Write-Host ""
Write-Host "The APY monitor will:" -ForegroundColor Cyan
Write-Host "  - Update vault data every 5 minutes" -ForegroundColor White
Write-Host "  - Store 7 days of historical APY data" -ForegroundColor White
Write-Host "  - Check alert conditions on each update" -ForegroundColor White
Write-Host "  - Send webhook notifications when triggered" -ForegroundColor White
Write-Host ""
Write-Host "Setup a test webhook at: https://webhook.site" -ForegroundColor Yellow
