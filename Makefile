# ============================================
# Check Splitter — Makefile
# ============================================
# Convenience targets for development and deployment

.PHONY: help dev test lint migrate build deploy tf-init tf-plan tf-apply tf-destroy clean

SHELL := /bin/bash
PROJECT_DIR := $(shell pwd)
TERRAFORM_DIR := $(PROJECT_DIR)/terraform

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ====== Development ======

dev: ## Run development server with auto-reload
	python run.py

test: ## Run test suite
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v

lint: ## Run linting checks
	python -m py_compile app/main.py
	@echo "Syntax OK"

# ====== Database ======

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

migrate-rollback: ## Rollback last migration
	alembic downgrade -1

# ====== Docker ======

build: ## Build Docker image locally
	docker build -t check-splitter:local .

run-docker: ## Run Docker container locally
	docker run --rm -p 8000:8000 \
		--env-file .env \
		-e ENVIRONMENT=development \
		-e RUN_MIGRATIONS=true \
		check-splitter:local

# ====== Terraform ======

tf-init: ## Initialize Terraform
	cd $(TERRAFORM_DIR) && terraform init

tf-plan: ## Preview infrastructure changes
	cd $(TERRAFORM_DIR) && terraform plan

tf-apply: ## Apply infrastructure changes
	cd $(TERRAFORM_DIR) && terraform apply

tf-destroy: ## Destroy all infrastructure (DANGER)
	cd $(TERRAFORM_DIR) && terraform destroy

tf-output: ## Show Terraform outputs
	cd $(TERRAFORM_DIR) && terraform output

# ====== Cloud Build ======

deploy: ## Deploy to Cloud Run via Cloud Build
	gcloud builds submit --config=cloudbuild.yaml .

deploy-manual: ## Manual deploy: build + push + deploy
	$(eval REGION := $(shell cd $(TERRAFORM_DIR) && terraform output -raw cloud_run_url 2>/dev/null | grep -oP '[\w-]+(?=\.run\.app)' || echo "europe-west1"))
	$(eval PROJECT := $(shell gcloud config get-value project))
	$(eval IMAGE := $(REGION)-docker.pkg.dev/$(PROJECT)/check-splitter/app:manual)
	docker build -t $(IMAGE) .
	docker push $(IMAGE)
	gcloud run services update check-splitter --region=$(REGION) --image=$(IMAGE)

# ====== Utilities ======

clean: ## Remove local build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage
	rm -rf check_splitter.db
	@echo "Cleaned."

setup: ## Initial project setup (install deps, create .env)
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — edit it with your settings"; \
	fi
	@echo "Setup complete! Run 'make dev' to start."
