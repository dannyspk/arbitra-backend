# Restart Backend with Live Trading WebSocket Enabled
# This script ensures ARB_ALLOW_LIVE_ORDERS is loaded and restarts the backend

Write-Host "🔧 Restarting Backend with Live Trading WebSocket..." -ForegroundColor Cyan
Write-Host ""

# Load .env file manually (in case python-dotenv isn't loading it)
if (Test-Path ".env") {
    Write-Host "📄 Loading .env file..." -ForegroundColor Yellow
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)\s*=\s*(.+)\s*$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
            Write-Host "   ✓ $key = $value" -ForegroundColor Green
        }
    }
    Write-Host ""
}

# Ensure ARB_ALLOW_LIVE_ORDERS is set
$env:ARB_ALLOW_LIVE_ORDERS = "1"
Write-Host "✅ ARB_ALLOW_LIVE_ORDERS = 1" -ForegroundColor Green
Write-Host ""

# Stop any existing Python processes
Write-Host "🛑 Stopping existing Python backend..." -ForegroundColor Yellow
Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start backend server
Write-Host "🚀 Starting backend server..." -ForegroundColor Cyan
Write-Host "   Command: python -m uvicorn src.arbitrage.web:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
Write-Host "📡 WebSocket endpoint will be available at: ws://127.0.0.1:8000/ws/live-dashboard" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Gray
Write-Host ""

python -m uvicorn src.arbitrage.web:app --reload --host 0.0.0.0 --port 8000
