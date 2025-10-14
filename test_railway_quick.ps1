# Quick Railway Staging Test
param(
    [Parameter(Mandatory=$true)]
    [string]$BaseUrl
)

Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "🧪 RAILWAY STAGING DEPLOYMENT - QUICK TEST" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Base URL: $BaseUrl" -ForegroundColor Yellow
Write-Host ""

$passed = 0
$failed = 0

# Test 1: Health Check
Write-Host "Test 1: Health Check" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET
    if ($response.status -eq "ok") {
        Write-Host "   ✅ PASS - Health check returned: $($response.status)" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "   ❌ FAIL - Unexpected response: $response" -ForegroundColor Red
        $failed++
    }
} catch {
    Write-Host "   ❌ FAIL - Error: $($_.Exception.Message)" -ForegroundColor Red
    $failed++
}

# Test 2: API Documentation
Write-Host "`nTest 2: API Documentation" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/docs" -Method GET
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ PASS - API docs accessible at /docs" -ForegroundColor Green
        $passed++
    }
} catch {
    Write-Host "   ❌ FAIL - API docs not accessible" -ForegroundColor Red
    $failed++
}

# Test 3: User Registration
Write-Host "`nTest 3: User Registration" -ForegroundColor Yellow
$randomUser = "test_$(Get-Random -Minimum 10000 -Maximum 99999)"
$registerBody = @{
    username = $randomUser
    email = "$randomUser@test.com"
    password = "TestPass123!"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/register" -Method POST -Body $registerBody -ContentType "application/json"
    if ($response.access_token) {
        Write-Host "   ✅ PASS - User registered successfully" -ForegroundColor Green
        Write-Host "   ✓ User ID: $($response.id)" -ForegroundColor Green
        Write-Host "   ✓ Token: $($response.access_token.Substring(0,20))..." -ForegroundColor Green
        $token = $response.access_token
        $passed++
    } else {
        Write-Host "   ❌ FAIL - No token received" -ForegroundColor Red
        $failed++
    }
} catch {
    Write-Host "   ❌ FAIL - Error: $($_.Exception.Message)" -ForegroundColor Red
    $failed++
}

# Test 4: User Login
Write-Host "`nTest 4: User Login" -ForegroundColor Yellow
$loginBody = @{
    username = $randomUser
    password = "TestPass123!"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    if ($response.access_token) {
        Write-Host "   ✅ PASS - Login successful" -ForegroundColor Green
        $token = $response.access_token
        $passed++
    } else {
        Write-Host "   ❌ FAIL - No token received" -ForegroundColor Red
        $failed++
    }
} catch {
    Write-Host "   ❌ FAIL - Error: $($_.Exception.Message)" -ForegroundColor Red
    $failed++
}

# Test 5: Get Current User (Protected Endpoint WITH Auth)
Write-Host "`nTest 5: Protected Endpoint (WITH Auth)" -ForegroundColor Yellow
if ($token) {
    try {
        $headers = @{
            "Authorization" = "Bearer $token"
        }
        $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/me" -Method GET -Headers $headers
        Write-Host "   ✅ PASS - Protected endpoint accessible with auth" -ForegroundColor Green
        Write-Host "   ✓ Username: $($response.username)" -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "   ❌ FAIL - Error: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
} else {
    Write-Host "   ⚠️  SKIP - No token available" -ForegroundColor Yellow
}

# Test 6: Protected Endpoint WITHOUT Auth (Should Fail)
Write-Host "`nTest 6: Protected Endpoint (WITHOUT Auth - Should Fail)" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/me" -Method GET -ErrorAction Stop
    Write-Host "   ❌ FAIL - Should require authentication but didn't" -ForegroundColor Red
    $failed++
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 401) {
        Write-Host "   ✅ PASS - Correctly rejected (401 Unauthorized)" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "   ❌ FAIL - Wrong status code: $statusCode" -ForegroundColor Red
        $failed++
    }
}

# Test 7: Invalid Token Rejection
Write-Host "`nTest 7: Invalid Token Rejection" -ForegroundColor Yellow
try {
    $headers = @{
        "Authorization" = "Bearer invalid_token_123"
    }
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/me" -Method GET -Headers $headers -ErrorAction Stop
    Write-Host "   ❌ FAIL - Should reject invalid token" -ForegroundColor Red
    $failed++
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 401) {
        Write-Host "   ✅ PASS - Invalid token correctly rejected" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "   ❌ FAIL - Wrong status code: $statusCode" -ForegroundColor Red
        $failed++
    }
}

# Summary
Write-Host "`n" + "=" * 80 -ForegroundColor Cyan
Write-Host "📊 TEST SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
$total = $passed + $failed
$percentage = [math]::Round(($passed / $total) * 100, 2)

Write-Host "Total Tests: $total" -ForegroundColor White
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })
Write-Host "Success Rate: $percentage%" -ForegroundColor $(if ($percentage -ge 90) { "Green" } elseif ($percentage -ge 70) { "Yellow" } else { "Red" })
Write-Host ""

if ($failed -eq 0) {
    Write-Host "🎉 ALL TESTS PASSED! Deployment is successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "✅ Your Railway staging deployment is working perfectly!" -ForegroundColor Green
    Write-Host "🌐 Deployment URL: $BaseUrl" -ForegroundColor Cyan
    Write-Host "📖 API Docs: $BaseUrl/docs" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host "⚠️  Some tests failed. Review the errors above." -ForegroundColor Yellow
    exit 1
}
