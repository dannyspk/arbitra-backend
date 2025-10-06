# Wallet Network Persistence Fix

## Issue
When a wallet was connected after being disconnected, the topbar displayed the correct network name. However, when the page was refreshed, the network would show as "Unknown" even though the wallet remained connected.

## Root Cause
The `chainId` state in the `WalletConnect` component was not being persisted to localStorage. While the wallet address and wallet type were saved and restored on page refresh, the network/chain ID was only stored in component state, causing it to be lost on refresh.

## Solution
Updated `WalletConnect.tsx` to persist the `chainId` to localStorage whenever it changes:

### Changes Made

1. **Added chainId to localStorage on initial connection:**
   - `connectMetaMask()`: Now saves `wallet_chain_id` to localStorage
   - `connectCoinbase()`: Now saves `wallet_chain_id` to localStorage

2. **Restore chainId from localStorage on page load:**
   - `checkConnection()`: Now reads `wallet_chain_id` from localStorage
   - Falls back to saved chainId if fetching from provider fails
   - Defaults to chain 1 (Ethereum) if no saved value exists

3. **Persist chainId when network changes:**
   - `handleChainChanged()`: Now saves updated chainId to localStorage
   - Event listeners in `checkConnection()`: Save chainId when provider emits chainChanged event
   - Event listeners in `connectCoinbase()`: Save chainId on network changes

4. **Clean up chainId on disconnect:**
   - `disconnect()`: Now removes `wallet_chain_id` from localStorage

## Testing
To verify the fix:

1. Connect a wallet (MetaMask or Coinbase Wallet)
2. Verify the network name displays correctly in the topbar
3. Disconnect the wallet
4. Reconnect the wallet
5. Verify the network name still displays correctly
6. **Refresh the page**
7. Verify the network name persists and doesn't show "Unknown"

## Technical Details

### localStorage Keys Used
- `wallet_address`: The connected wallet address
- `wallet_type`: Either 'metamask' or 'coinbase'
- `wallet_connected`: Boolean flag (legacy, kept for compatibility)
- `wallet_chain_id`: **NEW** - The numeric chain ID (e.g., 1 for Ethereum, 56 for BSC)

### Fallback Strategy
If fetching the current chainId from the provider fails during reconnection:
1. Use the saved `wallet_chain_id` from localStorage
2. If no saved value, default to chain 1 (Ethereum Mainnet)
3. Log a warning to console for debugging

## Files Modified
- `web/frontend/components/WalletConnect.tsx`

## Date
October 6, 2025
