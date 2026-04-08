#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Pull latest images from ECR and restart containers on EC2.
# Run on the EC2 instance. Expects IMAGE_TAG and ECR_REGISTRY env vars.
# =============================================================================
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-latest}"
ECR_REGISTRY="${ECR_REGISTRY:?ECR_REGISTRY must be set}"
AWS_REGION="${AWS_REGION:-us-east-1}"
COMPOSE_FILE="/home/ec2-user/devpulse/docker-compose.prod.yml"

echo "[deploy] Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "[deploy] Pulling images (tag: $IMAGE_TAG)..."
docker pull "$ECR_REGISTRY/devpulse:$IMAGE_TAG"
docker pull "$ECR_REGISTRY/devpulse-worker:$IMAGE_TAG"

echo "[deploy] Restarting services..."
cd /home/ec2-user/devpulse

ECR_REGISTRY="$ECR_REGISTRY" \
ECR_REPOSITORY="devpulse" \
IMAGE_TAG="$IMAGE_TAG" \
  docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "[deploy] Running database migrations..."
docker compose -f docker-compose.prod.yml exec -T api \
  alembic upgrade head

echo "[deploy] Health check..."
sleep 5
curl -sf http://localhost:8000/api/v1/health || { echo "[deploy] Health check failed!"; exit 1; }

echo "[deploy] Pruning old images..."
docker image prune -f

echo "[deploy] Done. Running containers:"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
