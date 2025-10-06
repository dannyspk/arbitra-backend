# Wallet Connection Debug Guide

## How to Debug the "Unknown" Network Issue

### Step 1: Open Browser Developer Console
1. Press `F12` or right-click and select "Inspect"
2. Click on the "Console" tab

### Step 2: Check localStorage
In the console, type:
```javascript
console.log({
  address: localStorage.getItem('wallet_address'),
  type: localStorage.getItem('wallet_type'),
  chainId: localStorage.getItem('wallet_chain_id'),
  connected: localStorage.getItem('wallet_connected')
})
```

### Step 3: Check Available Providers
In the console, type:
```javascript
console.log({
  ethereum: !!window.ethereum,
  isMetaMask: window.ethereum?.isMetaMask,
  isCoinbaseWallet: window.ethereum?.isCoinbaseWallet,
  providers: window.ethereum?.providers?.map(p => ({
    isMetaMask: p.isMetaMask,
    isCoinbaseWallet: p.isCoinbaseWallet
  })),
  coinbaseExtension: !!window.coinbaseWalletExtension
})
```

### Step 4: Refresh and Check Logs
After refreshing the page, look for these log messages:
- `"Provider not found for wallet type:"` - This means the wallet provider couldn't be detected
- `"Restoring chainId from localStorage:"` - ChainId was restored from storage
- `"Fetched chainId from provider:"` - ChainId was fetched from the wallet
- `"Failed to fetch chain ID, using saved value:"` - Fallback to saved chainId

### Step 5: Manual Test Connection
In the console, type:
```javascript
// For MetaMask
window.ethereum.request({ method: 'eth_accounts' }).then(accounts => {
  console.log('Accounts:', accounts)
  return window.ethereum.request({ method: 'eth_chainId' })
}).then(chainId => {
  console.log('ChainId:', parseInt(chainId, 16))
})
```

## Common Issues and Solutions

### Issue 1: Multiple Wallets Installed
**Symptom:** Network shows as "Unknown" after refresh when both MetaMask and Coinbase Wallet are installed.

**Solution:** 
- The code now includes fallback logic to use `window.ethereum` even if specific provider detection fails
- ChainId is restored from localStorage as a backup

### Issue 2: Provider Not Ready
**Symptom:** Provider detection fails intermittently.

**Solution:**
- Added 100ms delay before checking connection to allow providers to load
- This is now implemented in the latest update

### Issue 3: localStorage Not Saving
**Symptom:** ChainId is null in localStorage.

**Check:**
1. Open DevTools → Application → Local Storage → your domain
2. Look for `wallet_chain_id` key
3. If missing, the connection might not have completed successfully

**Solution:**
- Reconnect your wallet
- Check console for errors during connection
- Verify the chainId is being logged during connection

## Testing Checklist

- [ ] Connect wallet → Check console for "Fetched chainId from provider: [number]"
- [ ] Check localStorage → Verify `wallet_chain_id` exists
- [ ] Disconnect wallet → Verify `wallet_chain_id` is removed from localStorage  
- [ ] Reconnect wallet → Verify chainId is saved again
- [ ] Refresh page → Check console for provider detection logs
- [ ] Verify network name displays correctly (not "Unknown")

## Expected Console Output on Refresh

### Successful Connection:
```
Fetched chainId from provider: 1
```
or
```
Restoring chainId from localStorage: 1
```

### Failed Connection:
```
Provider not found for wallet type: metamask
Available providers: { ethereum: true, isMetaMask: true, ... }
Restoring chainId from localStorage: 1
```

Even if provider is not found, the chainId should be restored from localStorage.

## If Still Not Working

1. **Clear all wallet-related localStorage:**
```javascript
localStorage.removeItem('wallet_address')
localStorage.removeItem('wallet_type')
localStorage.removeItem('wallet_chain_id')
localStorage.removeItem('wallet_connected')
```

2. **Hard refresh:** `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)

3. **Reconnect wallet and note which provider is being used**

4. **Share the console logs** - especially the provider detection output
