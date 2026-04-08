#!/usr/bin/env bash
# =============================================================================
# setup_ec2.sh — EC2 user_data bootstrap for Amazon Linux 2023.
# Runs once on first boot via cloud-init. Installs Docker, CloudWatch agent,
# and registers a systemd service that starts the app on every boot.
# =============================================================================
set -euo pipefail

echo "[setup] Updating system packages..."
yum update -y

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
echo "[setup] Installing Docker..."
yum install -y docker
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

echo "[setup] Installing Docker Compose plugin..."
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

# ---------------------------------------------------------------------------
# CloudWatch agent
# ---------------------------------------------------------------------------
echo "[setup] Installing CloudWatch agent..."
yum install -y amazon-cloudwatch-agent
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

# ---------------------------------------------------------------------------
# Application directory
# ---------------------------------------------------------------------------
echo "[setup] Creating application directory..."
mkdir -p /home/ec2-user/devpulse
chown -R ec2-user:ec2-user /home/ec2-user/devpulse

# ---------------------------------------------------------------------------
# Systemd service — starts docker-compose.prod.yml on every boot
# ---------------------------------------------------------------------------
echo "[setup] Registering devpulse systemd service..."
cat > /etc/systemd/system/devpulse.service << 'EOF'
[Unit]
Description=DevPulse AI Application
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ec2-user/devpulse
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d --remove-orphans
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=300
User=ec2-user
Group=ec2-user

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable devpulse

echo "[setup] Bootstrap complete. EC2 is ready for first deployment."
echo "[setup] Next: run deploy.sh to push images and start the app."
