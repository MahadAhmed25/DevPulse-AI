.PHONY: dev test lint migrate worker infra-plan infra-apply deploy

dev:
	docker-compose up

test:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check app tests && ruff format --check app tests

migrate:
	alembic upgrade head

worker:
	celery -A app.workers.celery_app worker --loglevel=info

infra-plan:
	cd infra && terraform plan

infra-apply:
	cd infra && terraform apply

deploy:
	gh workflow run deploy.yml
