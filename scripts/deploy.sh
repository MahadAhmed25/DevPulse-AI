#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Called by GitHub Actions to deploy a new image to EC2.
# SSHes into the instance, pulls the new image from ECR, and restarts services.
#
# Required env vars:
#   EC2_HOST      — public IP or DNS of the EC2 instance
#   ECR_URL       — full ECR registry URL (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com)
#   IMAGE_TAG     — Docker image tag to deploy (e.g. git SHA)
#   AWS_REGION    — AWS region (default: us-east-1)
#
# The SSH key must be available as ~/.ssh/deploy_key (set up in CI secrets).
# =============================================================================
set -euo pipefail

EC2_HOST="${EC2_HOST:?EC2_HOST must be set}"
ECR_URL="${ECR_URL:?ECR_URL must be set}"
IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG must be set}"
AWS_REGION="${AWS_REGION:-us-east-1}"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=30 -i ~/.ssh/deploy_key"

echo "[deploy] Deploying image ${ECR_URL}:${IMAGE_TAG} to ${EC2_HOST}..."

ssh $SSH_OPTS "ec2-user@${EC2_HOST}" bash << REMOTE
set -euo pipefail

echo "[remote] Authenticating with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URL}"

echo "[remote] Pulling new image (tag: ${IMAGE_TAG})..."
docker pull "${ECR_URL}/devpulse-api:${IMAGE_TAG}"
docker pull "${ECR_URL}/devpulse-worker:${IMAGE_TAG}"

echo "[remote] Updating IMAGE_TAG in docker-compose.prod.yml..."
cd /home/ec2-user/devpulse
sed -i "s|IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|g" .env.prod 2>/dev/null || true
export ECR_URL="${ECR_URL}"
export IMAGE_TAG="${IMAGE_TAG}"

echo "[remote] Restarting api and worker containers..."
docker-compose -f docker-compose.prod.yml up -d --no-deps api worker

echo "[remote] Running database migrations..."
sleep 5
docker-compose -f docker-compose.prod.yml exec -T api alembic upgrade head

echo "[remote] Health check..."
curl -sf http://localhost:8000/api/v1/health || { echo "[remote] Health check failed!"; exit 1; }

echo "[remote] Pruning old images..."
docker image prune -f

echo "[remote] Deploy complete."
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
REMOTE

echo "[deploy] Done. ${EC2_HOST} is running image tag: ${IMAGE_TAG}"
