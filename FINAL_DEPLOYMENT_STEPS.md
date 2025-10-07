# Final Deployment Configuration

## Your Deployment URLs
- **Frontend (Vercel):** https://arbitra-six.vercel.app/
- **Backend (Railway):** https://arbitra-backend-production.up.railway.app

---

## Step 1: Update Railway CORS Settings

1. Go to Railway Dashboard: https://railway.app/dashboard
2. Select your **arbitra-backend** service
3. Click **Variables** tab
4. Find or add `ARB_ALLOW_ORIGINS` and set it to:
   ```
   https://arbitra-six.vercel.app,https://*.vercel.app,http://localhost:3000
   ```
5. Click **Add** or **Update**
6. Railway will automatically redeploy (takes ~1 minute)

---

## Step 2: Update Vercel Environment Variable

1. Go to: https://vercel.com/dannyspks-projects/arbitra/settings/environment-variables
2. Find `NEXT_PUBLIC_API_URL` (or add it if missing)
3. Set the value to:
   ```
   https://arbitra-backend-production.up.railway.app
   ```
4. Select environments: ✅ Production ✅ Preview ✅ Development
5. Click **Save**

---

## Step 3: Redeploy Vercel Frontend

1. Go to: https://vercel.com/dannyspks-projects/arbitra/deployments
2. Click the **⋯** (three dots) menu on your latest deployment
3. Select **Redeploy**
4. Wait 1-2 minutes for deployment to complete

---

## Step 4: Test Your Deployed Application

### Backend Health Check
```powershell
Invoke-RestMethod -Uri "https://arbitra-backend-production.up.railway.app/health"
```
Expected: `status: ok`

### Test API Endpoint
```powershell
Invoke-RestMethod -Uri "https://arbitra-backend-production.up.railway.app/api/opportunities" | ConvertTo-Json -Depth 3
```

### Frontend Tests
1. Visit: https://arbitra-six.vercel.app/
2. Open browser DevTools (F12) → Console tab
3. Check for:
   - ✅ No CORS errors
   - ✅ API calls go to Railway URL
   - ✅ Data loads successfully

### Wallet Connection Test
1. Click "Connect Wallet"
2. Connect MetaMask or Coinbase Wallet
3. Verify network name displays correctly (not "Unknown")
4. **Refresh the page** (F5)
5. ✅ Network name should **persist** (this was your original bug fix!)

---

## Troubleshooting

### If you see CORS errors:
- Verify `ARB_ALLOW_ORIGINS` in Railway includes your exact Vercel URL
- Wait for Railway to redeploy after changing environment variables
- Clear browser cache and hard refresh (Ctrl+Shift+R)

### If wallet network shows "Unknown" after refresh:
- Open browser DevTools → Application → Local Storage
- Check for `wallet_chain_id` key
- If missing, there may be a JavaScript error blocking the save

### If frontend shows "Failed to fetch":
- Verify `NEXT_PUBLIC_API_URL` in Vercel settings
- Ensure you redeployed after changing the variable
- Check Railway logs for backend errors

---

## Success Criteria ✅

Your deployment is complete when:
- ✅ Backend health check returns `{"status": "ok"}`
- ✅ Frontend loads without errors
- ✅ Wallet connects successfully
- ✅ Network name persists after page refresh
- ✅ Trading opportunities display correctly
- ✅ No CORS errors in browser console

---

## Quick Verification Script

```powershell
# Test backend
Write-Host "Testing backend health..." -ForegroundColor Cyan
Invoke-RestMethod -Uri "https://arbitra-backend-production.up.railway.app/health"

Write-Host "`nTesting opportunities endpoint..." -ForegroundColor Cyan
$opps = Invoke-RestMethod -Uri "https://arbitra-backend-production.up.railway.app/api/opportunities"
Write-Host "Opportunities found: $($opps.Count)" -ForegroundColor Green

Write-Host "`nBackend is working! Now test frontend at:" -ForegroundColor Green
Write-Host "https://arbitra-six.vercel.app/" -ForegroundColor Yellow
```

Save this as `test_deployment.ps1` and run it after completing the steps above.
