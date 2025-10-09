# Railway IP and API Key Checker
# Checks what public IP Railway is using and verifies API key configuration

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  RAILWAY IP & API KEY CHECKER" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backend = "https://arbitra-backend-production.up.railway.app"

Write-Host "Backend URL: $backend" -ForegroundColor Gray
Write-Host ""

# Check Railway's public IP
Write-Host "Checking Railway's Public IP..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$backend/api/debug/ip"
    
    if ($response.ip) {
        Write-Host "Railway Outbound IP: $($response.ip)" -ForegroundColor Green -BackgroundColor Black
        Write-Host ""
        Write-Host "Add this IP to your Binance API whitelist:" -ForegroundColor Cyan
        Write-Host "  1. Go to https://www.binance.com/en/my/settings/api-management"
        Write-Host "  2. Edit your API key"
        Write-Host "  3. Add IP: $($response.ip)" -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    Write-Host "Error fetching IP: $_" -ForegroundColor Red
    Write-Host "Make sure backend is deployed with /api/debug/my-ip endpoint" -ForegroundColor Yellow
}

# Check API key configuration
Write-Host "Checking API Key Configuration..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$backend/api/debug/config"
    
    Write-Host "API Key Status:" -ForegroundColor Cyan
    if ($response.binance_api_key_set) {
        Write-Host "  BINANCE_API_KEY: Configured" -ForegroundColor Green
        if ($response.api_key_preview) {
            Write-Host "    Preview: $($response.api_key_preview)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  BINANCE_API_KEY: NOT SET" -ForegroundColor Red
    }
    
    if ($response.binance_api_secret_set) {
        Write-Host "  BINANCE_API_SECRET: Configured" -ForegroundColor Green
    } else {
        Write-Host "  BINANCE_API_SECRET: NOT SET" -ForegroundColor Red
    }
    
    if ($response.allow_live_orders_set) {
        $value = if ($response.allow_live_orders_value -eq "1") { "ENABLED" } else { "DISABLED" }
        $color = if ($response.allow_live_orders_value -eq "1") { "Green" } else { "Yellow" }
        Write-Host "  ARB_ALLOW_LIVE_ORDERS: $value" -ForegroundColor $color
    }
    Write-Host ""
    
} catch {
    Write-Host "Error fetching API key info: $_" -ForegroundColor Red
}

# Test Binance connection
Write-Host "Testing Binance API Connection..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$backend/api/debug/test-binance"
    
    if ($response.success) {
        Write-Host "Successfully connected to Binance!" -ForegroundColor Green
        if ($response.account_type) {
            Write-Host "  Account Type: $($response.account_type)" -ForegroundColor White
        }
        if ($response.can_trade) {
            Write-Host "  Trading Permission: Enabled" -ForegroundColor Green
        }
    } else {
        Write-Host "Failed to connect to Binance" -ForegroundColor Red
        if ($response.error) {
            Write-Host "Error: $($response.error)" -ForegroundColor Yellow
            
            if ($response.error -like "*-2008*") {
                Write-Host ""
                Write-Host "This means the API key is invalid or doesn't exist" -ForegroundColor Cyan
                Write-Host "Fix: Check BINANCE_API_KEY in Railway variables" -ForegroundColor Green
            } elseif ($response.error -like "*-2015*" -or $response.error -like "*IP*") {
                Write-Host ""
                Write-Host "This means the IP is not whitelisted" -ForegroundColor Cyan
                Write-Host "Fix: Add Railway IP to Binance whitelist" -ForegroundColor Green
            }
        }
    }
    
} catch {
    Write-Host "Error testing Binance connection: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Done!" -ForegroundColor Green
Write-Host ""
