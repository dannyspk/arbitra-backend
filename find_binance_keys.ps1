# Script to find Binance API keys in various locations

Write-Host "`n🔍 Searching for Binance API Keys..." -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# 1. Check .env file
Write-Host "1. Checking .env file..." -ForegroundColor Yellow
$envFile = "C:\arbitrage\.env"
if (Test-Path $envFile) {
    Write-Host "✅ .env file exists" -ForegroundColor Green
    $envContent = Get-Content $envFile
    $apiKeyLine = $envContent | Select-String "BINANCE_API_KEY"
    $apiSecretLine = $envContent | Select-String "BINANCE_API_SECRET"
    
    if ($apiKeyLine) {
        Write-Host "   API Key: " -NoNewline -ForegroundColor White
        Write-Host $apiKeyLine -ForegroundColor Gray
    } else {
        Write-Host "   ❌ BINANCE_API_KEY not found" -ForegroundColor Red
    }
    
    if ($apiSecretLine) {
        Write-Host "   API Secret: " -NoNewline -ForegroundColor White
        $secretValue = ($apiSecretLine -split "=")[1]
        if ($secretValue -and $secretValue.Length -gt 10) {
            Write-Host "BINANCE_API_SECRET=" -NoNewline -ForegroundColor Gray
            Write-Host ($secretValue.Substring(0, 8) + "..." + $secretValue.Substring($secretValue.Length - 4)) -ForegroundColor Gray
        } else {
            Write-Host $apiSecretLine -ForegroundColor Gray
        }
    } else {
        Write-Host "   ❌ BINANCE_API_SECRET not found" -ForegroundColor Red
    }
    Write-Host ""
} else {
    Write-Host "❌ .env file not found at $envFile" -ForegroundColor Red
    Write-Host ""
}

# 2. Check environment variables
Write-Host "2. Checking system environment variables..." -ForegroundColor Yellow
$envApiKey = [System.Environment]::GetEnvironmentVariable("BINANCE_API_KEY", "User")
$envApiSecret = [System.Environment]::GetEnvironmentVariable("BINANCE_API_SECRET", "User")
$envApiKeyMachine = [System.Environment]::GetEnvironmentVariable("BINANCE_API_KEY", "Machine")
$envApiSecretMachine = [System.Environment]::GetEnvironmentVariable("BINANCE_API_SECRET", "Machine")

if ($envApiKey -or $envApiKeyMachine) {
    Write-Host "   ✅ BINANCE_API_KEY found in environment" -ForegroundColor Green
    if ($envApiKey) { Write-Host "      User: $envApiKey" -ForegroundColor Gray }
    if ($envApiKeyMachine) { Write-Host "      Machine: $envApiKeyMachine" -ForegroundColor Gray }
} else {
    Write-Host "   ❌ BINANCE_API_KEY not in environment variables" -ForegroundColor Red
}

if ($envApiSecret -or $envApiSecretMachine) {
    Write-Host "   ✅ BINANCE_API_SECRET found in environment" -ForegroundColor Green
} else {
    Write-Host "   ❌ BINANCE_API_SECRET not in environment variables" -ForegroundColor Red
}
Write-Host ""

# 3. Check common config locations
Write-Host "3. Checking common config file locations..." -ForegroundColor Yellow
$configPaths = @(
    "$env:USERPROFILE\.binance\config.json",
    "$env:USERPROFILE\.config\binance\credentials",
    "$env:APPDATA\Binance\config.json",
    "$env:LOCALAPPDATA\Binance\config.json",
    "C:\arbitrage\config\binance.json",
    "C:\arbitrage\.binance",
    "C:\arbitrage\credentials.json"
)

$foundConfig = $false
foreach ($path in $configPaths) {
    if (Test-Path $path) {
        Write-Host "   ✅ Found: $path" -ForegroundColor Green
        $foundConfig = $true
        try {
            $content = Get-Content $path -Raw
            if ($content -match "api.*key|apiKey|API_KEY") {
                Write-Host "      Contains API key references" -ForegroundColor Gray
            }
        } catch {
            Write-Host "      (Unable to read contents)" -ForegroundColor Gray
        }
    }
}

if (-not $foundConfig) {
    Write-Host "   ❌ No config files found" -ForegroundColor Red
}
Write-Host ""

# 4. Check Windows Credential Manager
Write-Host "4. Checking Windows Credential Manager..." -ForegroundColor Yellow
try {
    $creds = cmdkey /list | Select-String "binance" -CaseSensitive:$false
    if ($creds) {
        Write-Host "   ✅ Found Binance-related credentials:" -ForegroundColor Green
        $creds | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
    } else {
        Write-Host "   ❌ No Binance credentials in Credential Manager" -ForegroundColor Red
    }
} catch {
    Write-Host "   ⚠️  Unable to check Credential Manager" -ForegroundColor Yellow
}
Write-Host ""

# 5. Summary and recommendations
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "📋 Summary & Recommendations" -ForegroundColor Cyan
Write-Host ""

$hasKeys = ($apiKeyLine -or $envApiKey -or $envApiKeyMachine)

if ($hasKeys) {
    Write-Host "✅ API keys appear to be configured" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Test the API connection: python test_binance_api.py" -ForegroundColor White
    Write-Host "2. Review settings: Get-Content $envFile" -ForegroundColor White
} else {
    Write-Host "❌ No API keys found in common locations" -ForegroundColor Red
    Write-Host ""
    Write-Host "To configure API keys:" -ForegroundColor Yellow
    Write-Host "1. Get your API key from: https://www.binance.com/en/my/settings/api-management" -ForegroundColor White
    Write-Host "2. Run the setup script: .\setup_real_trading.ps1" -ForegroundColor White
    Write-Host "   OR" -ForegroundColor Gray
    Write-Host "3. Manually add to .env file:" -ForegroundColor White
    Write-Host "   BINANCE_API_KEY=your_key_here" -ForegroundColor Gray
    Write-Host "   BINANCE_API_SECRET=your_secret_here" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
