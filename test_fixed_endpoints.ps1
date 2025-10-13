#!/usr/bin/env pwsh
# Test AI Analysis and Social Sentiment endpoints after fix

$backend = "https://arbitra-backend-production.up.railway.app"

Write-Host "`n🧪 Testing Fixed Endpoints" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host ""

Write-Host "Waiting for Railway deployment..." -ForegroundColor Yellow
Write-Host "This test will retry for up to 3 minutes" -ForegroundColor Gray
Write-Host ""

$maxAttempts = 36  # 36 attempts x 5 seconds = 3 minutes
$attempt = 0
$deployed = $false

while ($attempt -lt $maxAttempts -and -not $deployed) {
    $attempt++
    Write-Host "Attempt $attempt/$maxAttempts..." -ForegroundColor Gray
    
    try {
        # Quick health check
        $health = Invoke-RestMethod "$backend/health" -ErrorAction Stop
        if ($health.status -eq "ok") {
            $deployed = $true
            Write-Host "✅ Railway is deployed!" -ForegroundColor Green
            Write-Host ""
            break
        }
    } catch {
        Write-Host "  Still deploying..." -ForegroundColor Gray
        Start-Sleep -Seconds 5
    }
}

if (-not $deployed) {
    Write-Host "`n❌ Deployment timeout. Check Railway dashboard:" -ForegroundColor Red
    Write-Host "  https://railway.app/dashboard" -ForegroundColor Cyan
    exit 1
}

# Test Social Sentiment
Write-Host "1️⃣ Testing Social Sentiment..." -ForegroundColor Yellow
try {
    $start = Get-Date
    $sentiment = Invoke-RestMethod "$backend/api/social-sentiment/BTC" -ErrorAction Stop
    $duration = ((Get-Date) - $start).TotalSeconds
    
    Write-Host "   ✅ SUCCESS ($([math]::Round($duration, 2))s)" -ForegroundColor Green
    Write-Host "   Sentiment: $($sentiment.sentiment_label)" -ForegroundColor Cyan
    Write-Host "   Score: $($sentiment.sentiment_score)" -ForegroundColor Cyan
    Write-Host "   Twitter: $($sentiment.twitter_sentiment)" -ForegroundColor Cyan
} catch {
    Write-Host "   ❌ FAILED: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) {
        $err = $_.ErrorDetails.Message | ConvertFrom-Json
        Write-Host "   Detail: $($err.detail)" -ForegroundColor Red
    }
}
Write-Host ""

# Test AI Analysis
Write-Host "2️⃣ Testing AI Analysis..." -ForegroundColor Yellow
try {
    $start = Get-Date
    $ai = Invoke-RestMethod "$backend/api/ai-analysis/BTCUSDT" -ErrorAction Stop
    $duration = ((Get-Date) - $start).TotalSeconds
    
    Write-Host "   ✅ SUCCESS ($([math]::Round($duration, 2))s)" -ForegroundColor Green
    Write-Host "   Overall Trend: $($ai.overall.trend)" -ForegroundColor Cyan
    Write-Host "   Confidence: $($ai.overall.confidence)%" -ForegroundColor Cyan
    Write-Host "   1h Trend: $($ai.'1h'.trend) ($($ai.'1h'.confidence)%)" -ForegroundColor Gray
    Write-Host "   4h Trend: $($ai.'4h'.trend) ($($ai.'4h'.confidence)%)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ FAILED: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) {
        $err = $_.ErrorDetails.Message | ConvertFrom-Json
        Write-Host "   Detail: $($err.detail)" -ForegroundColor Red
    }
}
Write-Host ""

# Test multiple requests (stress test)
Write-Host "3️⃣ Stress Test (5 concurrent requests)..." -ForegroundColor Yellow
$jobs = @()
1..5 | ForEach-Object {
    $jobs += Start-Job -ScriptBlock {
        param($url)
        try {
            $result = Invoke-RestMethod $url -ErrorAction Stop
            return @{ success = $true; time = (Get-Date) }
        } catch {
            return @{ success = $false; error = $_.Exception.Message }
        }
    } -ArgumentList "$backend/api/ai-analysis/ETHUSDT"
}

Start-Sleep -Seconds 10
$results = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job

$successful = ($results | Where-Object { $_.success }).Count
Write-Host "   Results: $successful/5 successful" -ForegroundColor $(if ($successful -eq 5) { "Green" } else { "Yellow" })

if ($successful -eq 5) {
    Write-Host "   ✅ All concurrent requests handled properly!" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Some requests failed (may be due to rate limiting)" -ForegroundColor Yellow
}
Write-Host ""

Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host "✅ Testing Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "The endpoints should now:" -ForegroundColor White
Write-Host "  • Respond quickly (< 5 seconds)" -ForegroundColor Gray
Write-Host "  • Not freeze or timeout" -ForegroundColor Gray
Write-Host "  • Handle concurrent requests" -ForegroundColor Gray
Write-Host ""
