# Using Multiple Wallets - Quick Guide

## Overview
The platform supports both **MetaMask** and **Coinbase Wallet**. However, only one can be active at a time since both inject into the same browser interface (`window.ethereum`).

## Option 1: Use MetaMask (Recommended for most users)

If you see the error "MetaMask is currently active", simply:

1. **Click "Connect MetaMask"** instead of Coinbase Wallet
2. Approve the connection
3. You're done! ✅

## Option 2: Switch to Coinbase Wallet

If you specifically want to use Coinbase Wallet:

### Method A: Disable MetaMask temporarily
1. Go to `chrome://extensions` (or browser extensions page)
2. Find **MetaMask** extension
3. Toggle it **OFF** (disable)
4. Refresh the page
5. Click **"Connect Coinbase Wallet"**
6. Approve the connection

### Method B: Use separate browser profiles
1. Create a new Chrome profile:
   - Click your profile icon → "Add" → "Continue without an account"
2. In the new profile:
   - Install only **Coinbase Wallet** extension
   - No MetaMask = No conflicts
3. Use this profile whenever you want Coinbase Wallet

### Method C: Use different browsers
- **Chrome/Brave** → MetaMask
- **Firefox** → Coinbase Wallet
- Keep them separated by browser

## Installing Coinbase Wallet

If you don't have Coinbase Wallet installed:

1. Visit: https://www.coinbase.com/wallet/downloads
2. Click **"Chrome Extension"** (or your browser)
3. Add to browser
4. Create or import your wallet
5. Return to the platform and click **"Connect Coinbase Wallet"**

## Which Wallet Should I Use?

### Use **MetaMask** if:
- ✅ You're already familiar with it
- ✅ You want the most popular option
- ✅ You use many DeFi protocols (best compatibility)
- ✅ You want advanced features and settings

### Use **Coinbase Wallet** if:
- ✅ You have a Coinbase account and want integration
- ✅ You prefer a simpler, cleaner interface
- ✅ You want built-in NFT management
- ✅ You're new to crypto (easier onboarding)

## Checking Which Wallet is Connected

Look at the icon next to your address:
- 🦊 **Orange icon** = MetaMask
- 💼 **Blue icon** = Coinbase Wallet
- 🔐 **Green icon** = Unknown wallet

## Switching Between Wallets

To switch from one wallet to another:

1. **Disconnect** current wallet (click "Disconnect" button)
2. **Disable** the current wallet extension (or switch browser profile)
3. **Click** the other wallet's connect button
4. **Approve** the connection

## Common Issues

### "Please switch to Coinbase Wallet or install it separately"
**Problem**: MetaMask is active, but you clicked Coinbase Wallet button

**Solutions**:
- Use MetaMask instead (easiest)
- Disable MetaMask and refresh page
- Install Coinbase Wallet if not installed

### "MetaMask not detected"
**Problem**: MetaMask extension is not installed or disabled

**Solutions**:
- Install from https://metamask.io/download
- Enable the extension if disabled
- Refresh the page after installation

### Both wallets installed, wrong one connects
**Problem**: Multiple wallet extensions conflict

**Solutions**:
- Disable unused wallet temporarily
- Use separate browser profiles (recommended)
- Use different browsers for different wallets

### Connection doesn't persist after refresh
**Problem**: Browser localStorage is disabled or cleared

**Solutions**:
- Enable cookies and site data in browser settings
- Check browser is not in incognito/private mode
- Whitelist the site in your privacy settings

## Security Tips

### ✅ DO:
- Keep both wallets updated to latest version
- Use hardware wallet integration when available
- Verify website URL before connecting
- Disconnect when not actively using the platform

### ❌ DON'T:
- Share your seed phrase with anyone
- Connect to untrusted websites
- Leave wallet unlocked when stepping away
- Use same password for wallet and email

## Mobile Usage

### Current Status: ⏳ Coming Soon
Mobile wallet support via **WalletConnect** is in development.

### Temporary Solution:
Use the mobile browser built into your wallet app:
- **MetaMask Mobile**: Built-in browser
- **Coinbase Wallet Mobile**: Built-in DApp browser

### Future Enhancement:
Once WalletConnect is implemented, you'll be able to:
1. Scan QR code on desktop
2. Approve connection on mobile
3. Sign transactions on your phone
4. Keep seed phrase secure on mobile device

## Browser Extension Links

### MetaMask
- Chrome: https://chrome.google.com/webstore/detail/metamask/nkbihfbeogaeaoehlefnkodbefgpgknn
- Firefox: https://addons.mozilla.org/en-US/firefox/addon/ether-metamask/
- Brave: Built-in support

### Coinbase Wallet
- Chrome: https://chrome.google.com/webstore/detail/coinbase-wallet-extension/hnfanknocfeofbddgcijnmhnfnkdnaad
- Downloads page: https://www.coinbase.com/wallet/downloads

## Need Help?

If you're still having issues:

1. **Check browser console** for error messages:
   - Press `F12` → Console tab
   - Look for red error messages
   
2. **Try basic troubleshooting**:
   - Clear browser cache
   - Disable other extensions temporarily
   - Try incognito mode (to rule out extension conflicts)
   
3. **Verify extension is working**:
   - Click the extension icon
   - Make sure wallet is unlocked
   - Check you have accounts created

4. **Check wallet version**:
   - Make sure you're using latest version
   - Update if outdated

## Technical Notes

### How Connection Works
```
1. User clicks "Connect [Wallet]" button
2. JavaScript checks window.ethereum for wallet
3. Requests account access via eth_requestAccounts
4. Wallet shows permission popup
5. User approves → address returned
6. Platform saves address to localStorage
7. Connection persists until disconnect or wallet removed
```

### What Data is Stored
Only public, non-sensitive data:
- ✅ Wallet address (public blockchain data)
- ✅ Chain ID (network identifier)
- ✅ Wallet type (MetaMask/Coinbase/Unknown)

NOT stored:
- ❌ Private keys
- ❌ Seed phrases
- ❌ Transaction history
- ❌ Personal information

## Future Wallet Support

Coming in Phase 2:
- 🔜 **WalletConnect** (mobile wallets)
- 🔜 **Trust Wallet** (via WalletConnect)
- 🔜 **Rainbow Wallet** (via WalletConnect)
- 🔜 **Ledger** (hardware wallet)
- 🔜 **Trezor** (hardware wallet)

## Summary

**For 99% of users**: Just use MetaMask - it's simpler and has the best compatibility.

**For Coinbase users**: Install Coinbase Wallet extension, disable MetaMask, then connect.

**For advanced users**: Use separate browser profiles to keep both wallets ready to use without conflicts.

The platform works equally well with either wallet - choose based on your preference! 🚀
