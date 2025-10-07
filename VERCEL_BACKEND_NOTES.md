# Vercel Deployment for FastAPI Backend

## ⚠️ Important Limitations

Vercel's serverless platform has limitations for this backend:

### Won't Work on Vercel:
- ❌ Background tasks (price monitoring, alerts)
- ❌ WebSocket connections (feeders)
- ❌ Startup/shutdown hooks
- ❌ Long-running processes
- ❌ Persistent connections

### Will Work:
- ✅ REST API endpoints
- ✅ Health checks
- ✅ Data queries
- ✅ Basic arbitrage scanning

## Better Alternatives

For full functionality, use:
1. **Railway** (Recommended) - Supports all features
2. **Render** - Supports background workers
3. **DigitalOcean App Platform** - Full app support
4. **AWS EC2** or **Heroku** - Complete control

## Deploy to Vercel Anyway (Limited Functionality)

If you want to deploy anyway for testing:

1. Make sure `vercel.json` exists in root
2. Run: `vercel --prod`
3. Or connect GitHub repo in Vercel dashboard

## Environment Variables for Vercel

Set these in Vercel dashboard:
- `ARB_ALLOW_ORIGINS` - Your frontend URLs
- `PORT` - 8000 (optional)
- API keys if needed

## Recommendation

**Use Railway for the backend** - it's free tier is generous and supports all your features including:
- Background workers
- WebSockets
- Long-running processes
- No cold starts
