#!/usr/bin/env bash
# =============================================================================
# setup_ec2.sh — Bootstrap script for a fresh Amazon Linux 2023 EC2 instance.
# Run once after provisioning. Installs Docker, aws-cli v2, and sets up dirs.
# =============================================================================
set -euo pipefail

echo "[setup] Updating system packages..."
sudo dnf update -y

echo "[setup] Installing Docker..."
sudo dnf install -y docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

echo "[setup] Installing Docker Compose plugin..."
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p "$DOCKER_CONFIG/cli-plugins"
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"

echo "[setup] Installing AWS CLI v2..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws/

echo "[setup] Creating application directory..."
mkdir -p /home/ec2-user/devpulse

echo "[setup] Creating .env file template (fill in values before deploying)..."
cat > /home/ec2-user/devpulse/.env << 'ENVEOF'
# Fill these in — never commit to git
DATABASE_URL=
REDIS_URL=
AWS_REGION=us-east-1
S3_BUCKET_NAME=
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
ANTHROPIC_API_KEY=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_WEBHOOK_SECRET=
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_PRO=
STRIPE_PRICE_TEAM=
FRONTEND_URL=
ENVIRONMENT=production
LOG_LEVEL=INFO
ENVEOF

echo "[setup] Done. Log out and back in for Docker group to take effect."
echo "[setup] Then copy docker-compose.prod.yml to /home/ec2-user/devpulse/ and run deploy.sh"
