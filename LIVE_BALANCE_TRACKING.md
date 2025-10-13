# Live Balance Tracking with Fees & PNL

## Overview
The Live Balance now shows a **comprehensive breakdown** of your Binance Futures account, including:
- ✅ Wallet Balance (raw Binance balance)
- ✅ Unrealized PNL (from open positions)
- ✅ Realized PNL (from closed trades)
- ✅ Total Fees Paid (tracked across all trades)
- ✅ Available Balance (for placing orders)

## What Gets Tracked

### 1. **Entry Fees** (When Opening Position)
```python
# Fee Rate: 0.04% (Binance Futures taker fee)
order_value = entry_price * size
entry_fee = order_value * 0.0004

# Example: $100 position
# Fee = $100 * 0.0004 = $0.04
```

**When tracked:**
- As soon as live order executes on Binance
- Added to `total_fees_paid` counter
- Logged: `[FEES] Fee tracked: $0.04, Total fees: $0.04`

### 2. **Exit Fees** (When Closing Position)
```python
# Fee Rate: 0.04% (Binance Futures taker fee)
exit_value = exit_price * size
exit_fee = exit_value * 0.0004

# Example: $105 position (after price moved up)
# Fee = $105 * 0.0004 = $0.042
```

**When tracked:**
- When position is closed via live order
- Added to `total_fees_paid` counter
- Logged: `[FEES] Fee tracked: $0.042, Total fees: $0.082`

### 3. **Unrealized PNL** (Open Positions)
```python
# For LONG positions:
unrealized_pnl = (current_price - entry_price) * size

# For SHORT positions:
unrealized_pnl = (entry_price - current_price) * size
```

**Calculated:**
- Real-time based on current market price
- Updates as price moves
- Not yet realized (position still open)

### 4. **Realized PNL** (Closed Trades)
```python
# For LONG positions:
realized_pnl = (exit_price - entry_price) * size

# For SHORT positions:
realized_pnl = (entry_price - exit_price) * size
```

**Tracked:**
- When position is closed
- Already reflected in Binance wallet
- Accumulated across all closed trades

## Balance Display Breakdown

### Live Manual Trading Panel Shows:

```
┌─────────────────────────────────┐
│ Wallet:         $488.09         │  ← Raw Binance Futures balance
│ Unrealized PNL: +$2.45          │  ← From open positions (green if +, red if -)
│ Fees Paid:      -$0.082         │  ← Total fees across all trades
│ ──────────────────────────────  │
│ Available:      $488.09         │  ← What you can use for new orders
└─────────────────────────────────┘
```

### What Each Line Means:

1. **Wallet**: Current USDT balance in Binance Futures wallet
   - This already includes realized PNL from closed trades
   - Fees are already deducted by Binance from your wallet

2. **Unrealized PNL**: Profit/loss from current open positions
   - Green (+) if positions are profitable
   - Red (-) if positions are losing
   - Only shows if you have open positions

3. **Fees Paid**: Total trading fees paid on all live trades
   - Tracked separately for transparency
   - Includes both entry and exit fees
   - Only shows if fees > 0

4. **Available**: Free balance you can use for new orders
   - Excludes margin used by open positions
   - This is what you can actually trade with

## How Balance Changes

### Example Trading Scenario:

**Starting Balance:** $500.00

#### Trade 1: Open LONG Position
```
Action: Buy 0.01 BTC at $50,000
Position Value: $500
Entry Fee: $500 * 0.0004 = $0.20

Balance After:
- Wallet: $500.00 (unchanged yet)
- Used: $500 (locked in position)
- Available: $0 (minus fees from Binance)
- Fees Paid: $0.20
```

#### BTC Price Moves to $51,000
```
Unrealized PNL: ($51,000 - $50,000) * 0.01 = +$10

Balance Display:
- Wallet: $499.80 (fee deducted)
- Unrealized PNL: +$10.00
- Fees Paid: $0.20
- Available: ~$0
```

#### Trade 1: Close LONG Position
```
Action: Sell 0.01 BTC at $51,000
Exit Value: $510
Exit Fee: $510 * 0.0004 = $0.204
Realized PNL: +$10 - $0.20 - $0.204 = +$9.596

Balance After:
- Wallet: $509.596 (starting + PNL - fees)
- Unrealized PNL: $0 (no open positions)
- Fees Paid: $0.404 ($0.20 + $0.204)
- Available: $509.596
```

## API Response Structure

### `/api/binance/balance` Returns:

```json
{
  "success": true,
  "wallet_balance": 488.09,      // Raw Binance wallet balance
  "available": 488.09,            // Free balance for trading
  "used": 0.0,                    // Margin locked in positions
  "unrealized_pnl": 2.45,         // From open positions
  "realized_pnl": 15.30,          // Total from closed trades
  "total_fees_paid": 0.082,       // All fees tracked
  "net_balance": 490.54,          // wallet + unrealized PNL
  "balance": 490.54,              // Alias for backward compatibility
  "currency": "USDT"
}
```

## Code Implementation

### Backend (web.py)

**Track Entry Fee:**
```python
# After live order executes
order_value = actual_entry_price * size
entry_fee = order_value * 0.0004
dashboard.add_fee_paid(entry_fee)
```

**Track Exit Fee:**
```python
# After closing position
exit_value = actual_exit_price * position.size
exit_fee = exit_value * 0.0004
dashboard.add_fee_paid(exit_fee)
```

**Calculate Net Balance:**
```python
net_info = dashboard.calculate_net_balance(wallet_balance)
# Returns: wallet, unrealized_pnl, total_fees, net_balance, realized_pnl
```

### Frontend (LiveManualTradingPanel.tsx)

**Fetch Balance:**
```typescript
const balanceResponse = await fetch(`${backend}/api/binance/balance`)
const balanceData = await balanceResponse.json()

setBalance(balanceData.available)      // For order sizing
setBalanceInfo(balanceData)             // For display breakdown
```

**Display:**
```tsx
{balanceInfo ? (
  <div>
    <div>Wallet: ${balanceInfo.wallet_balance.toFixed(2)}</div>
    <div>Unrealized PNL: ${balanceInfo.unrealized_pnl.toFixed(2)}</div>
    <div>Fees Paid: -${balanceInfo.total_fees_paid.toFixed(4)}</div>
    <div>Available: ${balance.toFixed(2)}</div>
  </div>
) : (
  <div>Loading...</div>
)}
```

## Fee Calculation Details

### Binance Futures Fee Structure

**Taker Fee (Market Orders):** 0.04%
- Used when you place market orders
- Order executes immediately
- This is what we use for all manual trades

**Maker Fee (Limit Orders):** 0.02%
- Used when you place limit orders that sit in order book
- Not currently used in this system

### Why Track Fees Separately?

1. **Transparency**: See exactly how much you're paying in fees
2. **Performance Analysis**: Calculate net returns after fees
3. **Tax Reporting**: Total fees paid is useful for tax deductions
4. **Trading Strategy**: High-frequency strategies may lose money to fees

## Example Calculations

### Scenario: Day Trading BTC

```
Starting Balance: $1,000

Trade 1: LONG BTC
- Entry: $50,000 x 0.02 BTC = $1,000
- Entry Fee: $1,000 * 0.0004 = $0.40
- Exit: $50,500 x 0.02 BTC = $1,010
- Exit Fee: $1,010 * 0.0004 = $0.404
- Gross PNL: $10
- Net PNL: $10 - $0.40 - $0.404 = $9.196
- Fees: $0.804

Trade 2: SHORT BTC
- Entry: $50,500 x 0.02 BTC = $1,010
- Entry Fee: $1,010 * 0.0004 = $0.404
- Exit: $50,000 x 0.02 BTC = $1,000
- Exit Fee: $1,000 * 0.0004 = $0.40
- Gross PNL: $10
- Net PNL: $10 - $0.404 - $0.40 = $9.196
- Total Fees: $0.804 + $0.804 = $1.608

Final Balance: $1,000 + $9.196 + $9.196 = $1,018.392
Total Fees Paid: $1.608
Net Gain: $18.392 (1.84%)
```

### Break-Even Calculation

To break even on a trade with 0.04% taker fees:
```
Entry Fee: 0.04%
Exit Fee: 0.04%
Total Fees: 0.08%

Minimum price move needed: 0.08%

Example:
- Entry at $50,000
- Need exit at: $50,000 * 1.0008 = $50,040 (or higher)
```

## Benefits of This System

✅ **Full Transparency**: See exactly where your money is
✅ **Real-time PNL**: Know your profit/loss instantly
✅ **Fee Awareness**: Understand the cost of trading
✅ **Better Decisions**: Make informed choices based on net returns
✅ **Accurate Tracking**: No surprises when checking Binance

## Notes

- Fees are automatically deducted by Binance from your wallet
- We track them separately for visibility only
- Unrealized PNL is not in your wallet until you close the position
- Available balance excludes margin locked in open positions
- All calculations use USDT as the quote currency
