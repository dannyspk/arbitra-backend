# Deploy to Google Cloud Platform (GCP)

This guide will help you deploy your trading backend to GCP with a static IP address.

## Prerequisites

1. Google Cloud account
2. gcloud CLI installed
3. Project created in GCP console

## Step 1: Install Google Cloud SDK

```powershell
# Download and install from: https://cloud.google.com/sdk/docs/install
# Or use chocolatey:
choco install gcloudsdk
```

## Step 2: Initialize and Login

```powershell
# Login to Google Cloud
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable compute.googleapis.com
```

## Step 3: Deploy to Cloud Run

```powershell
# Build and deploy
gcloud run deploy arbitra-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## Step 4: Set Environment Variables

```powershell
gcloud run services update arbitra-backend \
  --region us-central1 \
  --update-env-vars ARB_ALLOW_LIVE_ORDERS=1,BINANCE_API_KEY=your_key,BINANCE_API_SECRET=your_secret
```

## Step 5: Configure Static IP (For Binance Whitelist)

### Create VPC Connector

```powershell
# Create VPC network
gcloud compute networks create arbitra-network --subnet-mode=auto

# Create serverless VPC connector
gcloud compute networks vpc-access connectors create arbitra-connector \
  --network arbitra-network \
  --region us-central1 \
  --range 10.8.0.0/28
```

### Create Cloud NAT with Static IP

```powershell
# Reserve a static IP
gcloud compute addresses create arbitra-ip --region=us-central1

# Get the IP address (add this to Binance whitelist)
gcloud compute addresses describe arbitra-ip --region=us-central1 --format="get(address)"

# Create Cloud Router
gcloud compute routers create arbitra-router \
  --network arbitra-network \
  --region us-central1

# Create NAT configuration with static IP
gcloud compute routers nats create arbitra-nat \
  --router arbitra-router \
  --region us-central1 \
  --nat-external-ip-pool arbitra-ip \
  --nat-all-subnet-ip-ranges
```

### Update Cloud Run to Use VPC Connector

```powershell
gcloud run services update arbitra-backend \
  --region us-central1 \
  --vpc-connector arbitra-connector \
  --vpc-egress all-traffic
```

## Step 6: Update Frontend

Get your Cloud Run URL:
```powershell
gcloud run services describe arbitra-backend --region us-central1 --format="get(status.url)"
```

Update `web/frontend/vercel.json`:
```json
{
  "env": {
    "NEXT_PUBLIC_API_URL": "https://arbitra-backend-xxxxx-uc.a.run.app"
  }
}
```

## Step 7: Add Static IP to Binance

1. Get your static IP:
   ```powershell
   gcloud compute addresses describe arbitra-ip --region=us-central1 --format="get(address)"
   ```

2. Go to Binance → API Management
3. Add the static IP to whitelist
4. Enable Futures trading

## Pricing Estimate

- **Cloud Run**: ~$0.10/day (with moderate usage)
- **VPC Connector**: ~$0.08/hour (~$60/month)
- **Cloud NAT**: ~$0.045/hour (~$32/month)
- **Static IP**: ~$0.005/hour (~$3.60/month)

**Total**: ~$95-100/month

## Alternative: Compute Engine (Cheaper for Always-On)

If you need 24/7 availability, a small VM might be cheaper:

```powershell
# Create a small VM with static IP
gcloud compute instances create arbitra-backend \
  --machine-type e2-micro \
  --zone us-central1-a \
  --address arbitra-ip \
  --tags http-server,https-server

# SSH into the VM and set up your app
gcloud compute ssh arbitra-backend --zone us-central1-a
```

**Pricing**: ~$7-10/month for e2-micro instance

## Monitoring and Logs

```powershell
# View logs
gcloud run services logs read arbitra-backend --region us-central1 --limit 50

# Monitor service
gcloud run services describe arbitra-backend --region us-central1
```

## Cleanup (if needed)

```powershell
# Delete Cloud Run service
gcloud run services delete arbitra-backend --region us-central1

# Delete NAT and networking
gcloud compute routers nats delete arbitra-nat --router arbitra-router --region us-central1
gcloud compute routers delete arbitra-router --region us-central1
gcloud compute addresses delete arbitra-ip --region us-central1
gcloud compute networks vpc-access connectors delete arbitra-connector --region us-central1
gcloud compute networks delete arbitra-network
```

## Support

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud NAT Documentation](https://cloud.google.com/nat/docs)
- [VPC Connector Documentation](https://cloud.google.com/vpc/docs/configure-serverless-vpc-access)
