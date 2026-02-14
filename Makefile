# ============================================
# Check Splitter — Makefile
# ============================================
# Convenience targets for development and deployment

.PHONY: help dev test lint format migrate build run-docker dev-docker deploy deploy-cloudbuild deploy-manual tf-init tf-plan tf-apply tf-destroy tf-output tf-enable-remote-state clean setup

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

lint: ## Run linting checks (matches CI)
	black --check --diff app/ tests/
	isort --check --diff app/ tests/
	@echo "Lint OK"

format: ## Auto-format code with black + isort
	black app/ tests/
	isort app/ tests/
	@echo "Formatted."

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

run-docker: ## Run Docker container locally (production-like)
	docker run --rm -p 8000:8000 \
		--env-file .env \
		-e ENVIRONMENT=development \
		-e RUN_MIGRATIONS=true \
		check-splitter:local

dev-docker: ## Run with Docker Compose + live source mount (dev mode)
	docker compose up --build

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

tf-enable-remote-state: ## Migrate Terraform state to GCS remote backend
	@BUCKET=$$(cd $(TERRAFORM_DIR) && terraform output -raw tfstate_bucket 2>/dev/null); \
	if [ -z "$$BUCKET" ] || [ "$$BUCKET" = "N/A (not created)" ]; then \
		echo "Error: No tfstate bucket found. Run 'make tf-apply' with create_tfstate_bucket=true first."; \
		exit 1; \
	fi; \
	echo "Migrating state to GCS bucket: $$BUCKET"; \
	cd $(TERRAFORM_DIR) && \
	sed -i.bak 's|# backend "gcs"|backend "gcs"|; s|#   bucket = "<YOUR_TFSTATE_BUCKET_NAME>"|  bucket = "'$$BUCKET'"|; s|#   prefix = "terraform/state"|  prefix = "terraform/state"|; s|# }|}|' main.tf && \
	rm -f main.tf.bak && \
	terraform init -migrate-state && \
	echo "State migrated to GCS bucket: $$BUCKET"

# ====== Deployment ======

deploy: ## Show canonical deploy instructions
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  Canonical deploys happen via GitHub Actions CI/CD:        ║"
	@echo "║    git push origin main                                    ║"
	@echo "║                                                            ║"
	@echo "║  For manual fallback via Cloud Build:                      ║"
	@echo "║    make deploy-cloudbuild                                  ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"

deploy-cloudbuild: ## Deploy to Cloud Run via Cloud Build (manual fallback)
	gcloud builds submit --config=cloudbuild.yaml .

deploy-manual: ## Manual deploy: build + push + deploy (emergency use)
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
