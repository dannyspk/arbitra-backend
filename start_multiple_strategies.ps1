# Script to start multiple strategies on different symbols

Write-Host "`n=== Multiple Strategy Manager ===" -ForegroundColor Cyan
Write-Host ""

$backend = "http://127.0.0.1:8000"

# Function to start a strategy
function Start-Strategy {
    param(
        [string]$Symbol,
        [string]$Mode,
        [string]$Interval = "1m"
    )
    
    Write-Host "Starting $Mode strategy on $Symbol..." -ForegroundColor Yellow
    try {
        $body = @{
            symbol = $Symbol
            mode = $Mode
            interval = $Interval
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "$backend/api/live-strategy/start" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body
        
        if ($response.started) {
            Write-Host "  SUCCESS: $Symbol - $Mode mode started" -ForegroundColor Green
            Write-Host "  Active strategies: $($response.active_strategies)" -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "  FAILED: $($response.reason)" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
        return $false
    }
}

# Function to check current status
function Get-StrategyStatus {
    Write-Host "`nCurrent Active Strategies:" -ForegroundColor Cyan
    try {
        $status = Invoke-RestMethod -Uri "$backend/api/live-strategy/status"
        
        if ($status.running) {
            Write-Host "  Total Active: $($status.active_count)" -ForegroundColor Green
            Write-Host ""
            foreach ($strat in $status.strategies) {
                $modeEmoji = switch ($strat.mode) {
                    'bear' { '🐻' }
                    'bull' { '🐂' }
                    'scalp' { '⚡' }
                    'range' { '📊' }
                    default { '📈' }
                }
                Write-Host "  $modeEmoji $($strat.symbol) - $($strat.mode.ToUpper()) ($($strat.interval))" -ForegroundColor White
            }
        } else {
            Write-Host "  No strategies running" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
}

# Function to stop specific strategy
function Stop-Strategy {
    param([string]$Symbol)
    
    Write-Host "`nStopping strategy for $Symbol..." -ForegroundColor Yellow
    try {
        $body = @{ symbol = $Symbol } | ConvertTo-Json
        $response = Invoke-RestMethod -Uri "$backend/api/live-strategy/stop" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body
        
        if ($response.stopped) {
            Write-Host "  SUCCESS: $Symbol stopped" -ForegroundColor Green
            Write-Host "  Remaining: $($response.remaining_strategies)" -ForegroundColor Cyan
        } else {
            Write-Host "  FAILED: $($response.reason)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
}

# Function to stop all strategies
function Stop-AllStrategies {
    Write-Host "`nStopping ALL strategies..." -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri "$backend/api/live-strategy/stop" -Method POST
        
        if ($response.stopped) {
            Write-Host "  SUCCESS: Stopped $($response.count) strategies" -ForegroundColor Green
            Write-Host "  Stopped: $($response.stopped_strategies -join ', ')" -ForegroundColor Cyan
        } else {
            Write-Host "  FAILED: $($response.reason)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
}

# Interactive menu
while ($true) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "Multiple Strategy Manager" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Start SCALP strategy (BTCUSDT)" -ForegroundColor White
    Write-Host "2. Start BEAR strategy (SOLUSDT)" -ForegroundColor White
    Write-Host "3. Start BULL strategy (ETHUSDT)" -ForegroundColor White
    Write-Host "4. Start RANGE strategy (ADAUSDT)" -ForegroundColor White
    Write-Host "5. Start Custom strategy" -ForegroundColor White
    Write-Host "6. View active strategies" -ForegroundColor White
    Write-Host "7. Stop specific strategy" -ForegroundColor White
    Write-Host "8. Stop ALL strategies" -ForegroundColor White
    Write-Host "9. Quick Start (BTCUSDT Scalp + SOLUSDT Bear)" -ForegroundColor White
    Write-Host "Q. Quit" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "Select option"
    
    switch ($choice.ToUpper()) {
        '1' {
            Start-Strategy -Symbol "BTCUSDT" -Mode "scalp"
        }
        '2' {
            Start-Strategy -Symbol "SOLUSDT" -Mode "bear"
        }
        '3' {
            Start-Strategy -Symbol "ETHUSDT" -Mode "bull"
        }
        '4' {
            Start-Strategy -Symbol "ADAUSDT" -Mode "range"
        }
        '5' {
            $sym = Read-Host "Enter symbol (e.g., BTCUSDT)"
            Write-Host "Modes: bear, bull, scalp, range"
            $mode = Read-Host "Enter mode"
            $interval = Read-Host "Enter interval (default: 1m)"
            if ([string]::IsNullOrWhiteSpace($interval)) { $interval = "1m" }
            Start-Strategy -Symbol $sym -Mode $mode -Interval $interval
        }
        '6' {
            Get-StrategyStatus
        }
        '7' {
            Get-StrategyStatus
            $sym = Read-Host "`nEnter symbol to stop"
            if (![string]::IsNullOrWhiteSpace($sym)) {
                Stop-Strategy -Symbol $sym
            }
        }
        '8' {
            $confirm = Read-Host "Stop ALL strategies? (yes/no)"
            if ($confirm -eq "yes") {
                Stop-AllStrategies
            }
        }
        '9' {
            Write-Host "`nQuick Start: Multiple Strategies" -ForegroundColor Cyan
            Start-Strategy -Symbol "BTCUSDT" -Mode "scalp"
            Start-Sleep -Seconds 1
            Start-Strategy -Symbol "SOLUSDT" -Mode "bear"
            Start-Sleep -Seconds 1
            Get-StrategyStatus
        }
        'Q' {
            Write-Host "`nExiting..." -ForegroundColor Cyan
            break
        }
        default {
            Write-Host "Invalid option" -ForegroundColor Red
        }
    }
}

Write-Host "`nDone!" -ForegroundColor Green
Write-Host ""
