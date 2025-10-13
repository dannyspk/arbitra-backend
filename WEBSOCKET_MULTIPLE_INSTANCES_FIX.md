**CRITICAL FIX: Multiple LiveDashboard Instances Creating WebSocket Loop**

## Problem Found
There are **2 instances** of `<LiveDashboard>` on the trading page:
- Line 885: Trading tab (with hideSignals=true, hideHeader=true)
- Line 1219: Strategies tab  

Each instance calls `useLiveDashboardWebSocket()`, creating **2 WebSocket connections** that conflict with each other!

## Solution
Move the WebSocket hook to the parent component (page.tsx) and pass the data down as props.

## Implementation
See the fix applied in page.tsx
