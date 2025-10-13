# Quick Backend Restart Script
Write-Host "🔄 Restarting backend to apply WebSocket position fix..." -ForegroundColor Cyan
Write-Host ""

# Stop Python processes
Write-Host "Stopping Python processes..." -ForegroundColor Yellow
Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start backend
Write-Host "Starting backend with position import fix..." -ForegroundColor Green
Write-Host ""
python -m uvicorn src.arbitrage.web:app --reload --host 0.0.0.0 --port 8000
