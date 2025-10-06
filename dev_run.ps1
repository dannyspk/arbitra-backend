# Run backend (uvicorn) and frontend (npm run dev) concurrently in separate PowerShell windows

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start backend in a new PowerShell: use the python -m uvicorn invocation and set PYTHONPATH so the package is importable
$backendCmd = "cd $root; `$env:PYTHONPATH=\"$root\\src\"; python -m uvicorn arbitrage.web:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCmd)

# Start frontend dev server in a new PowerShell
$frontendCmd = "cd $root\web\frontend; npm run dev"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCmd)
