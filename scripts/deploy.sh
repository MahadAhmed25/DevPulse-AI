#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Runs ON EC2 (called remotely by GitHub Actions via SSH).
# Pulls new images from ECR and restarts services via docker-compose.
#
# Required env vars (passed by deploy.yml SSH command):
#   ECR_REGISTRY  — ECR registry hostname (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com)
#   IMAGE_TAG     — Docker image tag to deploy (git SHA)
# =============================================================================
set -euo pipefail

ECR_REGISTRY="${ECR_REGISTRY:?ECR_REGISTRY must be set}"
IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG must be set}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "[deploy] Deploying ${ECR_REGISTRY}/devpulse:${IMAGE_TAG}..."

echo "[deploy] Authenticating with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "[deploy] Pulling new images..."
docker pull "${ECR_REGISTRY}/devpulse:${IMAGE_TAG}"
docker pull "${ECR_REGISTRY}/devpulse-worker:${IMAGE_TAG}"

echo "[deploy] Updating IMAGE_TAG in .env.prod..."
cd /home/ec2-user/devpulse
sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|g" .env.prod 2>/dev/null || true

export ECR_REGISTRY="${ECR_REGISTRY}"
export IMAGE_TAG="${IMAGE_TAG}"

echo "[deploy] Restarting containers..."
docker-compose -f docker-compose.prod.yml up -d --no-deps --remove-orphans redis api worker

echo "[deploy] Running database migrations..."
sleep 15
docker-compose -f docker-compose.prod.yml exec -T api alembic upgrade head

echo "[deploy] Health check..."
curl --retry 10 --retry-delay 3 --retry-connrefused -sf \
  http://localhost:8000/api/v1/health || { echo "[deploy] Health check failed!"; exit 1; }

echo "[deploy] Pruning old images..."
docker image prune -f

echo "[deploy] Deploy complete."
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
