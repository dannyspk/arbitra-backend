#!/bin/bash
# Automated DigitalOcean Droplet Setup Script
# Run this on your DigitalOcean droplet after initial creation

set -e  # Exit on error

echo "🚀 Setting up Arbitra Trading Backend on DigitalOcean"
echo "=================================================="
echo ""

# Update system
echo "📦 Step 1/8: Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
echo "✅ System updated"
echo ""

# Install dependencies
echo "📦 Step 2/8: Installing dependencies..."
apt-get install -y -qq python3 python3-pip python3-venv git nginx supervisor ufw
echo "✅ Dependencies installed"
echo ""

# Create application directory
echo "📁 Step 3/8: Setting up application directory..."
mkdir -p /opt/arbitra-backend
cd /opt/arbitra-backend
echo "✅ Directory created"
echo ""

# Clone repository
echo "📥 Step 4/8: Cloning repository..."
if [ -d ".git" ]; then
    echo "Repository already exists, pulling latest changes..."
    git pull
else
    git clone https://github.com/dannyspk/arbitra-backend.git .
fi
echo "✅ Repository cloned"
echo ""

# Setup Python environment
echo "🐍 Step 5/8: Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✅ Python environment ready"
echo ""

# Create environment file
echo "⚙️  Step 6/8: Creating environment configuration..."
cat > /opt/arbitra-backend/.env <<'EOF'
# API Configuration
ARB_ALLOW_LIVE_ORDERS=1

# Binance API Credentials (REPLACE THESE!)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here

# Risk Management
ARB_MAX_POSITION_SIZE=10
ARB_MAX_DAILY_TRADES=5
ARB_MAX_LOSS_PERCENT=1

# CORS
ARB_ALLOW_ORIGINS=*
EOF

chmod 600 /opt/arbitra-backend/.env
echo "✅ Environment file created at /opt/arbitra-backend/.env"
echo "⚠️  IMPORTANT: Edit this file and add your Binance API credentials!"
echo ""

# Create systemd service
echo "🔧 Step 7/8: Creating system service..."
cat > /etc/systemd/system/arbitra.service <<'EOF'
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

systemctl daemon-reload
systemctl enable arbitra
echo "✅ System service created"
echo ""

# Setup Nginx
echo "🌐 Step 8/8: Configuring Nginx..."
cat > /etc/nginx/sites-available/arbitra <<'EOF'
server {
    listen 80;
    server_name _;
    
    client_max_body_size 10M;
    
    # Increase timeouts for WebSocket
    proxy_read_timeout 3600;
    proxy_connect_timeout 3600;
    proxy_send_timeout 3600;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

ln -sf /etc/nginx/sites-available/arbitra /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl restart nginx
echo "✅ Nginx configured"
echo ""

# Setup firewall
echo "🔥 Setting up firewall..."
ufw --force allow 22
ufw --force allow 80
ufw --force allow 443
ufw --force enable
echo "✅ Firewall enabled"
echo ""

# Get server IP
SERVER_IP=$(curl -s ifconfig.me)

echo "=================================================="
echo "✅ Installation Complete!"
echo "=================================================="
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Edit environment file with your API credentials:"
echo "   nano /opt/arbitra-backend/.env"
echo ""
echo "2. Start the service:"
echo "   systemctl start arbitra"
echo ""
echo "3. Check service status:"
echo "   systemctl status arbitra"
echo ""
echo "4. View logs:"
echo "   journalctl -u arbitra -f"
echo ""
echo "5. Test the API:"
echo "   curl http://localhost:8000/health"
echo "   curl http://$SERVER_IP/health"
echo ""
echo "6. Add this IP to Binance whitelist:"
echo "   📌 $SERVER_IP"
echo ""
echo "7. Update your frontend vercel.json:"
echo "   NEXT_PUBLIC_API_URL=http://$SERVER_IP"
echo ""
echo "=================================================="
echo "🎉 Your backend will be available at:"
echo "   http://$SERVER_IP"
echo "=================================================="
