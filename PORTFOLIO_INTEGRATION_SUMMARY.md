# Portfolio Balance Enhancement - Exchange + Wallet Integration

## Overview
Updated the Dashboard to show a **comprehensive portfolio value** that combines:
1. **Exchange Balances** (Binance + MEXC)
2. **Web3 Wallet Balances** (Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Avalanche)

## Backend Implementation

### New Endpoint: `/api/wallet/balance/{address}`

```python
@app.get('/api/wallet/balance/{address}')
async def get_wallet_balance(address: str, chains: str = 'ethereum,bsc,polygon,arbitrum,optimism,base,avalanche'):
```

**Features:**
- Fetches native token balances from multiple chains via RPC
- Supports 7 major chains by default
- Gets real-time USD prices from CoinGecko API
- Returns total USD value across all chains

**Supported Chains:**
| Chain | Native Token | RPC Endpoint | CoinGecko ID |
|-------|-------------|--------------|--------------|
| Ethereum | ETH | https://eth.llamarpc.com | ethereum |
| BSC | BNB | https://bsc-dataseed1.binance.org | binancecoin |
| Polygon | MATIC | https://polygon-rpc.com | matic-network |
| Arbitrum | ETH | https://arb1.arbitrum.io/rpc | ethereum |
| Optimism | ETH | https://mainnet.optimism.io | ethereum |
| Base | ETH | https://mainnet.base.org | ethereum |
| Avalanche | AVAX | https://api.avax.network/ext/bc/C/rpc | avalanche-2 |

**Response Format:**
```json
{
  "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "chains_checked": ["ethereum", "bsc", "polygon", ...],
  "balances": [
    {
      "chain": "Ethereum",
      "token": "ETH",
      "balance": 1.234,
      "balance_usd": 4321.56,
      "price_usd": 3500.00
    },
    ...
  ],
  "total_usd": 12345.67,
  "timestamp": "2025-10-06T12:34:56.789Z"
}
```

## Frontend Implementation

### Dashboard Page Updates (`app/page.tsx`)

#### 1. Added Wallet State
```typescript
const [connectedWallet, setConnectedWallet] = useState<string | null>(null)
```

#### 2. Enhanced Portfolio Calculation
```typescript
// Fetch portfolio balance from exchanges
let exchangePortfolioValue = 0
let walletPortfolioValue = 0

// Calculate exchange balances (Binance + MEXC)
exchangePortfolioValue = calculatePortfolioValue(binanceBalances) + 
                         calculatePortfolioValue(mexcBalances)

// Fetch Web3 wallet balance if connected
if (connectedWallet) {
  const walletBalRes = await fetch(`${API}/api/wallet/balance/${connectedWallet}`)
  if (walletBalRes.ok) {
    const walletData = await walletBalRes.json()
    walletPortfolioValue = walletData.total_usd || 0
  }
}

// Combine both sources
const totalPortfolioValue = exchangePortfolioValue + walletPortfolioValue
```

#### 3. Wallet Connection Handlers
```typescript
const handleWalletConnect = (address: string) => {
  setConnectedWallet(address)
  // Triggers re-fetch of dashboard data
}

const handleWalletDisconnect = () => {
  setConnectedWallet(null)
  // Updates portfolio to show only exchange balances
}
```

#### 4. Auto-Refresh on Wallet Connection
```typescript
useEffect(() => {
  fetchDashboardData()
  const interval = setInterval(fetchDashboardData, 30000)
  return () => clearInterval(interval)
}, [connectedWallet]) // ← Re-fetches when wallet connects/disconnects
```

#### 5. Pass Callbacks to WalletConnect
```typescript
<WalletConnect 
  onConnect={handleWalletConnect} 
  onDisconnect={handleWalletDisconnect} 
/>
```

### WalletConnect Component Updates

#### Added `onDisconnect` Callback
```typescript
export default function WalletConnect({ 
  onConnect,
  onDisconnect 
}: { 
  onConnect?: (address: string) => void
  onDisconnect?: () => void
}) {
```

#### Call Callback on Disconnect
```typescript
function disconnect() {
  setAddress(null)
  setChainId(null)
  setWalletType('unknown')
  localStorage.removeItem('wallet_address')
  localStorage.removeItem('wallet_connected')
  localStorage.removeItem('wallet_type')
  onDisconnect?.() // ← Notify parent component
}
```

## User Experience

### Before Connection
**"Your Portfolio"** card shows:
- Exchange balances only (Binance + MEXC)
- Value calculated from CEX balances × ticker prices

### After Wallet Connection
**"Your Portfolio"** card shows:
- ✅ Exchange balances (Binance + MEXC)
- ✅ Wallet balances (ETH, BNB, MATIC, etc. across 7 chains)
- 📊 **Total combined USD value**

### Real-Time Updates
1. **Connect Wallet** → Immediately adds wallet balance
2. **Disconnect Wallet** → Removes wallet balance, shows only exchanges
3. **Switch Accounts** → Automatically updates to new account's balance
4. **Auto-Refresh** → Updates every 30 seconds

## Example Scenarios

### Scenario 1: No Wallet Connected
```
Exchange Balances:
- Binance: $5,000 USDT
- MEXC: $2,000 USDT

Total Portfolio: $7,000
```

### Scenario 2: Wallet Connected
```
Exchange Balances:
- Binance: $5,000 USDT
- MEXC: $2,000 USDT

Wallet Balances:
- Ethereum: 1.5 ETH = $5,250
- BSC: 2.0 BNB = $1,200
- Polygon: 500 MATIC = $400

Total Portfolio: $13,850
```

### Scenario 3: Multi-Chain Holdings
```
Exchange Balances:
- Binance: $10,000
- MEXC: $3,000

Wallet Balances:
- Ethereum (mainnet): 2.0 ETH = $7,000
- Arbitrum: 0.5 ETH = $1,750
- Optimism: 0.3 ETH = $1,050
- Base: 1.0 ETH = $3,500
- BSC: 5.0 BNB = $3,000
- Polygon: 1000 MATIC = $800
- Avalanche: 50 AVAX = $1,750

Total Portfolio: $31,850
```

## Technical Implementation Details

### RPC Calls
```javascript
// For each chain, make eth_getBalance call
POST https://eth.llamarpc.com
{
  "jsonrpc": "2.0",
  "method": "eth_getBalance",
  "params": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb", "latest"],
  "id": 1
}

Response:
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": "0x152d02c7e14af6800000" // Wei amount (hex)
}

// Convert: 1.5 ETH = 0x152d02c7e14af6800000 wei
```

### Price Fetching
```javascript
GET https://api.coingecko.com/api/v3/simple/price?ids=ethereum,binancecoin,matic-network,avalanche-2&vs_currencies=usd

Response:
{
  "ethereum": {"usd": 3500},
  "binancecoin": {"usd": 600},
  "matic-network": {"usd": 0.80},
  "avalanche-2": {"usd": 35}
}
```

### Calculation Example
```python
# Ethereum balance
balance_wei = int("0x152d02c7e14af6800000", 16)  # 1500000000000000000000
balance_eth = balance_wei / 10**18                # 1.5 ETH
usd_price = 3500                                   # $3,500 per ETH
balance_usd = 1.5 * 3500                          # $5,250

# Repeat for all chains and sum
total_wallet_usd = sum(all_chain_balances)
```

## Performance Considerations

### Caching
- Price data cached for 60 seconds (avoid rate limiting)
- RPC calls made in parallel for all chains
- Only fetches when wallet is connected

### Error Handling
- Graceful fallback if RPC fails for a chain
- Continues calculating other chains
- Console logs errors without breaking UI

### Network Efficiency
```typescript
// Parallel fetching
const [binanceBalRes, mexcBalRes, walletBalRes] = await Promise.all([
  fetch('/api/balances/binance'),
  fetch('/api/balances/mexc'),
  connectedWallet ? fetch(`/api/wallet/balance/${connectedWallet}`) : null
])
```

## Future Enhancements

### Phase 2: ERC20 Token Support
- Detect and fetch ERC20 token balances
- Support USDT, USDC, DAI, WETH, etc.
- Multi-token portfolio view

### Phase 3: DeFi Protocol Integration
- Fetch staked positions (Aave, Compound, Yearn)
- Include LP token values (Uniswap, Curve, Balancer)
- Show lending/borrowing positions

### Phase 4: NFT Valuation
- Fetch NFT holdings via OpenSea API
- Estimate floor price values
- Include in total portfolio

### Phase 5: Historical Tracking
- Track portfolio value over time
- Show charts and performance metrics
- Compare against benchmarks (BTC, ETH, S&P 500)

## Testing Instructions

### Test 1: Without Wallet
1. Open Dashboard (don't connect wallet)
2. **Verify**: Portfolio shows only exchange balances
3. **Expected**: ~$7,000 (Binance + MEXC)

### Test 2: Connect MetaMask
1. Click "Connect Wallet" → "Connect MetaMask"
2. Approve connection
3. **Verify**: Portfolio increases immediately
4. **Expected**: $7,000 + wallet balance

### Test 3: Multiple Chains
1. Ensure you have balances on multiple chains
2. Connect wallet
3. Open browser console (F12)
4. Look for: `Wallet balance: $X.XX`
5. **Verify**: Matches sum of all chain balances

### Test 4: Disconnect
1. Click "Disconnect"
2. **Verify**: Portfolio returns to exchange-only value
3. **Expected**: Back to ~$7,000

### Test 5: Account Switch
1. Connect wallet
2. Note portfolio value
3. Switch to different account in MetaMask
4. **Verify**: Portfolio updates to new account's balance

### Test 6: Auto-Refresh
1. Connect wallet
2. Wait 30 seconds
3. Check console logs
4. **Verify**: Portfolio re-fetches automatically

## API Testing

### Test Backend Endpoint
```powershell
# Test with sample address
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/wallet/balance/0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb' | ConvertTo-Json -Depth 5

# Test with specific chains
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/wallet/balance/0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb?chains=ethereum,bsc' | ConvertTo-Json -Depth 5
```

## Files Modified

```
Backend:
- src/arbitrage/web.py
  ├─ Added get_wallet_balance() endpoint
  └─ RPC integration + CoinGecko price fetching

Frontend:
- web/frontend/app/page.tsx
  ├─ Added connectedWallet state
  ├─ Enhanced portfolio calculation
  ├─ Added wallet connection handlers
  └─ Updated useEffect dependency array

- web/frontend/components/WalletConnect.tsx
  ├─ Added onDisconnect prop
  └─ Call onDisconnect() callback
```

## Summary

✅ **Backend**: New `/api/wallet/balance/{address}` endpoint  
✅ **Frontend**: Wallet connection triggers portfolio re-calculation  
✅ **Integration**: Seamless combination of CEX + DEX balances  
✅ **UX**: Real-time updates when connecting/disconnecting wallet  
✅ **Multi-Chain**: Supports 7 major EVM chains out of the box  

**Result**: Users now see their complete financial picture across centralized exchanges and decentralized wallets in one unified view! 🚀
