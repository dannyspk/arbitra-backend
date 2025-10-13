#!/bin/bash
# Quick GCP Compute Engine deployment script

echo "🚀 Deploying Arbitra Backend to GCP Compute Engine"
echo ""

# Set your project ID
PROJECT_ID="your-gcp-project-id"
INSTANCE_NAME="arbitra-backend"
ZONE="us-central1-a"
MACHINE_TYPE="e2-micro"

echo "📋 Configuration:"
echo "  Project: $PROJECT_ID"
echo "  Instance: $INSTANCE_NAME"
echo "  Zone: $ZONE"
echo "  Type: $MACHINE_TYPE"
echo ""

# Create static IP
echo "1️⃣ Creating static IP..."
gcloud compute addresses create ${INSTANCE_NAME}-ip --region=us-central1

# Get the IP
STATIC_IP=$(gcloud compute addresses describe ${INSTANCE_NAME}-ip --region=us-central1 --format="get(address)")
echo "✅ Static IP created: $STATIC_IP"
echo "👉 Add this IP to Binance whitelist!"
echo ""

# Create instance
echo "2️⃣ Creating VM instance..."
gcloud compute instances create $INSTANCE_NAME \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --machine-type=$MACHINE_TYPE \
  --address=${INSTANCE_NAME}-ip \
  --tags=http-server,https-server \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB \
  --boot-disk-type=pd-standard \
  --metadata=startup-script='#!/bin/bash
    apt-get update
    apt-get install -y python3-pip python3-venv git nginx
    
    # Clone your repo (update with your repo)
    cd /opt
    git clone https://github.com/dannyspk/arbitra-backend.git
    cd arbitra-backend
    
    # Setup Python environment
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    
    # Create systemd service
    cat > /etc/systemd/system/arbitra.service <<EOF
[Unit]
Description=Arbitra Trading Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/arbitra-backend
Environment="PATH=/opt/arbitra-backend/venv/bin"
Environment="ARB_ALLOW_LIVE_ORDERS=1"
Environment="BINANCE_API_KEY=your_key_here"
Environment="BINANCE_API_SECRET=your_secret_here"
ExecStart=/opt/arbitra-backend/venv/bin/uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Start service
    systemctl daemon-reload
    systemctl enable arbitra
    systemctl start arbitra
    
    # Setup nginx reverse proxy
    cat > /etc/nginx/sites-available/arbitra <<EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
    
    ln -s /etc/nginx/sites-available/arbitra /etc/nginx/sites-enabled/
    rm /etc/nginx/sites-enabled/default
    systemctl restart nginx
  '

echo "✅ VM instance created!"
echo ""

# Create firewall rules
echo "3️⃣ Creating firewall rules..."
gcloud compute firewall-rules create allow-http \
  --project=$PROJECT_ID \
  --allow tcp:80 \
  --target-tags http-server

gcloud compute firewall-rules create allow-https \
  --project=$PROJECT_ID \
  --allow tcp:443 \
  --target-tags https-server

echo "✅ Firewall configured!"
echo ""

echo "🎉 Deployment complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Add this IP to Binance whitelist: $STATIC_IP"
echo "2. SSH into instance to set environment variables:"
echo "   gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
echo "3. Edit /etc/systemd/system/arbitra.service with your API keys"
echo "4. Restart service: sudo systemctl restart arbitra"
echo "5. Update frontend URL to: http://$STATIC_IP"
echo ""
echo "🔍 Useful commands:"
echo "  View logs: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo journalctl -u arbitra -f'"
echo "  Check status: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo systemctl status arbitra'"
