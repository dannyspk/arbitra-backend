# Wallet Address Tracking - Implementation Details

## Overview
The system now properly tracks the **specific wallet address** the user has connected with, not just a generic "wallet" connection. This handles:
- Users with multiple addresses in their wallet
- Account switching within the wallet
- Real-time updates when the active account changes

## How Address Tracking Works

### Initial Connection Flow

```
User clicks "Connect MetaMask/Coinbase"
         ↓
Wallet shows account selector
         ↓
User selects specific address (e.g., Account 2)
         ↓
Wallet returns: ["0x742d35..."]
         ↓
WalletConnect sets: address = "0x742d35..."
         ↓
Calls: onConnect("0x742d35...")
         ↓
Dashboard sets: connectedWallet = "0x742d35..."
         ↓
API called: /api/wallet/balance/0x742d35...
         ↓
Portfolio shows balance for THAT specific address
```

### Account Switching Flow

```
User has Address A connected (0x742d35...)
         ↓
User switches to Address B in wallet (0x9f8e7d...)
         ↓
Wallet fires: accountsChanged(["0x9f8e7d..."])
         ↓
Event handler updates: address = "0x9f8e7d..."
         ↓
Calls: onConnect("0x9f8e7d...")
         ↓
Dashboard updates: connectedWallet = "0x9f8e7d..."
         ↓
useEffect triggers (dependency: connectedWallet)
         ↓
Fetches data for NEW address
         ↓
Portfolio updates to show Address B balance
```

## Key Implementation Details

### 1. WalletConnect Component

#### State Management
```typescript
const [address, setAddress] = useState<string | null>(null)
```
Stores the **exact address** the user connected with, not just a boolean "connected" state.

#### Event Listener Setup
```typescript
// For MetaMask
window.ethereum.on('accountsChanged', handleAccountsChanged)

// For Coinbase
coinbaseProvider.on('accountsChanged', (accounts: string[]) => {
  if (accounts.length > 0) {
    setAddress(accounts[0])
    localStorage.setItem('wallet_address', accounts[0])
    onConnect?.(accounts[0]) // ← Notify parent with new address
  }
})
```

#### Parent Notification
```typescript
function handleAccountsChanged(accounts: string[]) {
  if (accounts.length === 0) {
    disconnect()
  } else {
    setAddress(accounts[0])
    localStorage.setItem('wallet_address', accounts[0])
    onConnect?.(accounts[0]) // ← Always pass the current address
  }
}
```

### 2. Dashboard Component

#### Address State
```typescript
const [connectedWallet, setConnectedWallet] = useState<string | null>(null)
```
Stores the currently active wallet address (not just "connected: true/false").

#### Wallet Connection Handler
```typescript
const handleWalletConnect = (address: string) => {
  setConnectedWallet(address) // ← Store specific address
}
```

#### API Call with Specific Address
```typescript
if (connectedWallet) {
  const walletBalRes = await fetch(
    `${API}/api/wallet/balance/${connectedWallet}` // ← Uses exact address
  )
  // ...
}
```

#### Re-fetch on Address Change
```typescript
useEffect(() => {
  fetchDashboardData()
  // ...
}, [connectedWallet]) // ← Dependency array includes address
```

When `connectedWallet` changes (user switches accounts), the entire effect re-runs and fetches data for the new address.

### 3. Visual Feedback

The portfolio card shows which address is being tracked:

```tsx
{connectedWallet && (
  <p className="text-xs text-slate-500 mt-2">
    <span className="text-slate-400">Wallet: </span>
    {connectedWallet.slice(0, 6)}...{connectedWallet.slice(-4)}
  </p>
)}
```

Displays: "Wallet: 0x742d...0bEb"

## User Scenarios

### Scenario 1: User Has 3 Addresses in MetaMask

**Wallet Accounts:**
- Account 1: 0x1234...5678 (Main - 5 ETH)
- Account 2: 0xabcd...ef01 (Trading - 10 ETH)  ← User selects this
- Account 3: 0x9876...5432 (Cold Storage - 50 ETH)

**What Happens:**
1. User clicks "Connect MetaMask"
2. MetaMask shows all 3 accounts
3. User selects **Account 2** (0xabcd...ef01)
4. Dashboard fetches balance for **0xabcd...ef01 only**
5. Portfolio shows: 10 ETH = $35,000
6. Card shows: "Wallet: 0xabcd...ef01"

**Account 3's 50 ETH is NOT included** (as it should be - user only connected Account 2).

### Scenario 2: User Switches Accounts

**Initial State:**
- Connected: Account 2 (0xabcd...ef01) with 10 ETH
- Portfolio shows: $35,000

**User Action:**
1. Opens MetaMask extension
2. Clicks "Switch Account"
3. Selects Account 1 (0x1234...5678)

**Automatic Response:**
1. MetaMask fires `accountsChanged` event
2. WalletConnect detects: ["0x1234...5678"]
3. Updates address to: 0x1234...5678
4. Calls `onConnect("0x1234...5678")`
5. Dashboard re-fetches data
6. API calls `/api/wallet/balance/0x1234...5678`
7. Portfolio updates to: $17,500 (5 ETH)
8. Card updates to: "Wallet: 0x1234...5678"

**Result: Portfolio automatically tracks the active account!**

### Scenario 3: User Disconnects One Account

**Initial State:**
- Account 2 connected (0xabcd...ef01)
- Portfolio showing Account 2 balance

**User Action:**
1. Opens MetaMask
2. Clicks "Connected sites"
3. Clicks "Disconnect" for Account 2

**Automatic Response:**
1. MetaMask fires `accountsChanged([])` (empty array)
2. WalletConnect detects empty array
3. Calls `disconnect()`
4. `onDisconnect()` called
5. Dashboard sets `connectedWallet = null`
6. Portfolio stops including wallet balance
7. Shows only exchange balances

## Backend Integration

The backend endpoint receives the **exact address**:

```python
@app.get('/api/wallet/balance/{address}')
async def get_wallet_balance(address: str, ...):
    # address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    # Fetches balance for THIS specific address only
    
    for chain in chain_list:
        response = requests.post(
            config['rpc'],
            json={
                'jsonrpc': '2.0',
                'method': 'eth_getBalance',
                'params': [address, 'latest'],  # ← Specific address
                'id': 1
            }
        )
```

## Persistence Across Sessions

### localStorage Tracking
```javascript
// On connection
localStorage.setItem('wallet_address', '0x742d35...')
localStorage.setItem('wallet_type', 'metamask')

// On page reload
const savedAddress = localStorage.getItem('wallet_address')
// Reconnect to that specific address
```

### Auto-Reconnect with Correct Address
```typescript
async function checkConnection() {
  const savedAddress = localStorage.getItem('wallet_address')
  const accounts = await provider.request({ method: 'eth_accounts' })
  
  if (accounts.length > 0 && accounts[0] === savedAddress) {
    // Still connected to same address
    setAddress(accounts[0])
    onConnect?.(accounts[0])
  } else {
    // Address changed or disconnected
    localStorage.removeItem('wallet_address')
  }
}
```

## Testing the Implementation

### Test 1: Basic Connection
```
1. Have multiple accounts in MetaMask
2. Connect wallet
3. Select Account 2
4. Open browser console
5. Check: localStorage.getItem('wallet_address')
6. Verify: Shows Account 2's address (not Account 1)
```

### Test 2: Account Switching
```
1. Connect with Account A
2. Note portfolio value
3. Switch to Account B in wallet
4. Watch portfolio update automatically
5. Verify: New address shown in portfolio card
6. Verify: Console shows API call to new address
```

### Test 3: Persistence
```
1. Connect with Account B
2. Refresh page
3. Verify: Still shows Account B (not Account A)
4. Verify: Portfolio matches Account B balance
```

### Test 4: Multiple Tabs
```
1. Open Dashboard in Tab 1, connect Account A
2. Open Dashboard in Tab 2
3. Switch to Account B in wallet
4. Both tabs should update to show Account B
```

### Test 5: Direct API Test
```powershell
# Test with your actual address
$addr = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wallet/balance/$addr" | ConvertTo-Json

# Test with different address
$addr2 = "0x1234567890123456789012345678901234567890"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wallet/balance/$addr2" | ConvertTo-Json

# Results should be different (different balances)
```

## Security Considerations

### Why This Approach is Secure

1. **No Private Key Access**
   - Only reads public address
   - Cannot sign transactions without user approval
   
2. **User Controls Address**
   - Wallet always prompts for account selection
   - User explicitly chooses which address to connect
   
3. **Read-Only Balance Queries**
   - Only calls `eth_getBalance` (read-only)
   - No write operations possible

4. **Address Validation**
   - Backend can add checksum validation
   - Frontend displays address for user verification

### What Users See in Wallet

When connecting:
```
[MetaMask Popup]
────────────────────────────────
Connect with MetaMask

Select an account:
○ Account 1  0x1234...5678  5.2 ETH
● Account 2  0xabcd...ef01  10.5 ETH  ← Selected
○ Account 3  0x9876...5432  50.0 ETH

[Cancel]  [Next]
────────────────────────────────
```

User consciously chooses which address to connect.

## Common Questions

### Q: What if user has balances on multiple addresses?
**A:** They need to connect each address separately, or we could add support for multiple simultaneous connections (future enhancement).

### Q: Can we track all their addresses automatically?
**A:** No - that would require access we don't have. User must explicitly connect each address they want tracked.

### Q: What if they switch accounts while app is closed?
**A:** On next load, `checkConnection()` verifies the saved address is still active. If user switched while app was closed, it clears the connection and they need to reconnect.

### Q: Can we detect all addresses in their wallet?
**A:** No - wallets only expose the currently selected address via `eth_accounts`. We cannot enumerate all addresses in their wallet (this is by design for privacy).

## Summary

✅ **Specific Address Tracking**: Uses exact address user connected with  
✅ **Account Switching**: Auto-detects and updates when user switches  
✅ **Event-Driven Updates**: Real-time response to wallet changes  
✅ **Visual Feedback**: Shows current address in portfolio card  
✅ **Persistent Sessions**: Remembers address across page reloads  
✅ **Privacy Preserved**: Only accesses explicitly connected address  

**Result**: Users see accurate portfolio data for their **current active wallet address**, with automatic updates when they switch accounts! 🎯
