# Deploy to DigitalOcean ($6/month with Static IP)

This guide will help you deploy your trading backend to DigitalOcean with a static IP for Binance whitelisting.

## Step 1: Create DigitalOcean Account

1. Go to https://www.digitalocean.com
2. Sign up for an account (get $200 free credit for 60 days with referral)
3. Add a payment method

## Step 2: Create a Droplet (VM)

1. Click **"Create"** → **"Droplets"**
2. **Choose an image:**
   - Select **Ubuntu 22.04 LTS**
3. **Choose a plan:**
   - Basic Plan
   - Regular CPU
   - **$6/month** (1GB RAM, 1 vCPU, 25GB SSD)
4. **Choose a datacenter region:**
   - Select closest to you (e.g., New York, San Francisco, London)
5. **Authentication:**
   - Choose **SSH Key** (recommended) or **Password**
   - If SSH: Click "New SSH Key" and follow instructions
6. **Finalize:**
   - Hostname: `arbitra-backend`
   - Click **"Create Droplet"**

## Step 3: Get Your Static IP

1. Wait for droplet to be created (~60 seconds)
2. **Your droplet's IP address is shown** - this is your static IP!
3. **Important:** Copy this IP address - you'll add it to Binance whitelist

## Step 4: Connect to Your Droplet

### Using PowerShell (Windows):

```powershell
# Replace with your droplet's IP
ssh root@YOUR_DROPLET_IP
```

If using password, enter it when prompted.

## Step 5: Install Dependencies on Droplet

Once connected via SSH, run these commands:

```bash
# Update system
apt-get update
apt-get upgrade -y

# Install Python and dependencies
apt-get install -y python3 python3-pip python3-venv git nginx

# Install supervisor (to keep app running)
apt-get install -y supervisor

# Create app directory
mkdir -p /opt/arbitra-backend
cd /opt/arbitra-backend
```

## Step 6: Clone Your Repository

```bash
# Clone your backend repo
git clone https://github.com/dannyspk/arbitra-backend.git .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

## Step 7: Set Environment Variables

```bash
# Create .env file
cat > /opt/arbitra-backend/.env <<EOF
ARB_ALLOW_LIVE_ORDERS=1
BINANCE_API_KEY=mCKNY0bBb5ZjWDRGwUpynLuGum6wHEOdCWKieqZSPUv8Q4qwiYgWlwWTtXZtXP23
BINANCE_API_SECRET=9mt3IjYLzzpUtJvpBESJRp1vKLjItxrMbyC0vSk8NrVYqrjL75tBGe3kQjBTmcGB
ARB_MAX_POSITION_SIZE=10
ARB_MAX_DAILY_TRADES=5
ARB_MAX_LOSS_PERCENT=1
EOF

# Secure the .env file
chmod 600 /opt/arbitra-backend/.env
```

## Step 8: Create Systemd Service

```bash
# Create service file
cat > /etc/systemd/system/arbitra.service <<EOF
[Unit]
Description=Arbitra Trading Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/arbitra-backend
Environment="PATH=/opt/arbitra-backend/venv/bin"
EnvironmentFile=/opt/arbitra-backend/.env
ExecStart=/opt/arbitra-backend/venv/bin/uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable arbitra
systemctl start arbitra

# Check status
systemctl status arbitra
```

## Step 9: Setup Nginx Reverse Proxy

```bash
# Create Nginx configuration
cat > /etc/nginx/sites-available/arbitra <<EOF
server {
    listen 80;
    server_name _;
    
    # Increase timeouts for WebSocket
    proxy_read_timeout 3600;
    proxy_connect_timeout 3600;
    proxy_send_timeout 3600;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/arbitra /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default

# Test and restart Nginx
nginx -t
systemctl restart nginx
```

## Step 10: Setup Firewall

```bash
# Allow SSH, HTTP, and HTTPS
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable

# Check status
ufw status
```

## Step 11: Test Your Backend

```bash
# Test locally on the droplet
curl http://localhost:8000/health

# From your computer, test the public IP
# Open browser: http://YOUR_DROPLET_IP/health
```

## Step 12: Add IP to Binance Whitelist

1. Go to Binance → **API Management**
2. Find your API key
3. Click **Edit**
4. Under **IP Access Restrictions:**
   - Add your DigitalOcean droplet IP
5. Enable **Futures Trading**
6. Save

## Step 13: Update Frontend

Update your frontend to use the DigitalOcean backend:

```powershell
# On your local machine
cd c:\arbitrage\web\frontend
```

Edit `vercel.json`:
```json
{
  "env": {
    "NEXT_PUBLIC_API_URL": "http://YOUR_DROPLET_IP"
  }
}
```

Then commit and push:
```powershell
git add vercel.json
git commit -m "Update backend URL to DigitalOcean"
git push origin main
```

## Step 14: (Optional) Add SSL Certificate

For HTTPS, use Let's Encrypt (free):

```bash
# Install certbot
apt-get install -y certbot python3-certbot-nginx

# Get certificate (replace with your domain)
certbot --nginx -d yourdomain.com

# Certbot will automatically configure Nginx for HTTPS
```

## Useful Commands

### View Logs
```bash
# Real-time logs
journalctl -u arbitra -f

# Last 100 lines
journalctl -u arbitra -n 100
```

### Restart Service
```bash
systemctl restart arbitra
```

### Update Code
```bash
cd /opt/arbitra-backend
git pull
systemctl restart arbitra
```

### Check Service Status
```bash
systemctl status arbitra
```

### Monitor Resources
```bash
# Check CPU and memory usage
htop

# Or
top
```

## Automatic Deployment (Optional)

Create a webhook to auto-deploy when you push to GitHub:

```bash
# Install webhook
apt-get install -y webhook

# Create deploy script
cat > /opt/arbitra-backend/deploy.sh <<EOF
#!/bin/bash
cd /opt/arbitra-backend
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart arbitra
EOF

chmod +x /opt/arbitra-backend/deploy.sh
```

## Backup Your Droplet

DigitalOcean offers automatic backups:
1. Go to your Droplet settings
2. Enable **Backups** (adds 20% to monthly cost = ~$1.20/month)

## Monthly Costs

- **Droplet**: $6/month
- **Backups (optional)**: $1.20/month
- **Total**: $6-7/month

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
journalctl -u arbitra -n 50

# Check if port 8000 is in use
netstat -tulpn | grep 8000
```

### Can't connect from outside
```bash
# Check firewall
ufw status

# Check if Nginx is running
systemctl status nginx

# Check if backend is running
systemctl status arbitra
```

### API errors
```bash
# Check environment variables are loaded
systemctl show arbitra | grep Environment

# Test API directly
curl http://localhost:8000/api/dashboard
```

## Security Best Practices

1. ✅ Never commit `.env` file to git
2. ✅ Use SSH keys instead of passwords
3. ✅ Keep system updated: `apt-get update && apt-get upgrade`
4. ✅ Monitor logs regularly
5. ✅ Enable automatic security updates
6. ✅ Disable root login after creating a sudo user

## Support

- DigitalOcean Docs: https://docs.digitalocean.com
- Community: https://www.digitalocean.com/community

---

## Quick Summary

1. ✅ Create $6/month droplet on DigitalOcean
2. ✅ SSH into droplet
3. ✅ Run setup commands above
4. ✅ Add droplet IP to Binance whitelist
5. ✅ Update frontend URL
6. ✅ Done! Your backend is live with static IP

**Total time:** ~15-20 minutes  
**Monthly cost:** $6
