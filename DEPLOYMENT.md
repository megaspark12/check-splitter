# Deployment Guide — Check Splitter on GCP

Production deployment using **Terraform** for infrastructure, **Cloud Build** for Docker image builds, and **Cloud Run** for serving.

## Architecture

```
┌─────────────┐     HTTPS     ┌──────────────────┐
│   Browser   │ ───────────▶  │    Cloud Run      │
│  (PWA/Web)  │ ◀───────────  │  (Gunicorn+Uvicorn│
└─────────────┘   WebSocket   │   2 workers)      │
                              └────────┬──────────┘
                                       │
                         ┌─────────────┼─────────────┐
                         │             │             │
                         ▼             ▼             ▼
                  ┌────────────┐ ┌──────────┐ ┌──────────────┐
                  │  Cloud SQL │ │   GCS    │ │   Secret     │
                  │ PostgreSQL │ │  Bucket  │ │   Manager    │
                  │   (15)     │ │ Receipts │ │ (API keys,   │
                  └────────────┘ └──────────┘ │  DB pass)    │
                         ▲                    └──────────────┘
                         │
                  ┌────────────┐
                  │    VPC     │
                  │ (private   │
                  │  network)  │
                  └────────────┘
```

### GCP Resources (managed by Terraform)

| Resource | Name / ID | Purpose |
|----------|-----------|---------|
| **Cloud Run** | `check-splitter` | Serves the application |
| **Cloud SQL** | `check-splitter-{suffix}` | PostgreSQL 15 database |
| **VPC Network** | `check-splitter-vpc` | Private networking for Cloud SQL |
| **VPC Connector** | `check-splitter-conn` | Cloud Run → Cloud SQL access |
| **Artifact Registry** | `check-splitter` | Docker image storage |
| **GCS Bucket** | `check-splitter-receipts-{suffix}` | Receipt image storage |
| **Secret Manager** | 3 secrets | `gemini-api-key`, `app-secret-key`, `db-password` |
| **Service Account** | `check-splitter-run@...` | Cloud Run identity with least-privilege IAM |
| **9 GCP APIs** | Various | run, sqladmin, secretmanager, artifactregistry, cloudbuild, vpcaccess, compute, storage, iam |

## Prerequisites

- **Google Cloud SDK** (`gcloud`) — [Install](https://cloud.google.com/sdk/docs/install)
- **Terraform** ≥ 1.5.0 — [Install](https://developer.hashicorp.com/terraform/install)
- **GCP Project** with billing enabled
- **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/apikey)

## Step-by-Step Deployment

### 1. Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Configure Terraform Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
project_id     = "your-gcp-project-id"
gemini_api_key = "AIza..."
region         = "europe-west1"          # or your preferred region

# Scaling (scale-to-zero for cost savings)
min_instances = 0
max_instances = 3

# Database (db-f1-micro is cheapest; use db-g1-small+ for real traffic)
db_tier              = "db-f1-micro"
deletion_protection  = false              # set true once stable
```

### 3. Initialize & Apply Terraform

```bash
terraform init
terraform plan          # Review the ~36 resources to be created
terraform apply         # Type 'yes' to confirm
```

This takes **15–20 minutes** (Cloud SQL creation is slow). Terraform creates:
- All GCP APIs enabled
- VPC network + private IP range + peering + connector
- Cloud SQL instance + database + user + password
- GCS bucket with 30-day lifecycle
- Secret Manager secrets (Gemini key, app secret, DB password)
- Artifact Registry repository
- Service account + IAM bindings
- Cloud Run service (will fail on first apply — image doesn't exist yet)

### 4. Build & Push Docker Image

```bash
cd ..  # back to project root

# Build via Cloud Build (no local Docker needed)
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/check-splitter/app:latest \
  --project PROJECT_ID \
  --region REGION
```

Replace `REGION` and `PROJECT_ID` with your values. Takes ~2 minutes.

### 5. Deploy Cloud Run

After the image is built, re-apply Terraform or deploy directly:

```bash
# Option A: Via Terraform (keeps state in sync)
cd terraform && terraform apply

# Option B: Via gcloud (faster for iterations)
gcloud run deploy check-splitter \
  --image REGION-docker.pkg.dev/PROJECT_ID/check-splitter/app:latest \
  --region REGION \
  --project PROJECT_ID
```

### 6. Verify

```bash
# Get the Cloud Run URL
URL=$(cd terraform && terraform output -raw cloud_run_url)

# Health check
curl -s "$URL/health" | python3 -m json.tool
# Expected: {"status": "healthy", "database": "connected", ...}

# Test session creation
curl -s -X POST "$URL/api/sessions" \
  -H "Content-Type: application/json" \
  -d '{"host_name": "Test"}' | python3 -m json.tool
# Expected: session object with code, participants, host_token
```

Open the Cloud Run URL in a browser to access the app.

## Database Migrations

Migrations run automatically on container startup via `entrypoint.sh` when `RUN_MIGRATIONS=true` (set by Terraform).

**How it works:**
1. Checks if `alembic_version` table exists in the database
2. **Fresh database** → runs `Base.metadata.create_all()` + `alembic stamp head` (creates all tables from models, marks Alembic as current)
3. **Existing database** → runs `alembic upgrade head` (applies pending migrations)

**Manual migration (if needed):**
```bash
# Create a new migration locally
alembic revision --autogenerate -m "description"

# Rebuild & redeploy to apply
gcloud builds submit --tag ...
cd terraform && terraform apply
```

## Configuration Reference

All environment variables are set via Terraform (Cloud Run env + Secret Manager):

| Variable | Source | Description |
|----------|--------|-------------|
| `ENVIRONMENT` | Terraform env | `production` — disables /docs, /redoc |
| `WORKERS` | Terraform env | Gunicorn workers (default: 2) |
| `RUN_MIGRATIONS` | Terraform env | `true` — run Alembic on startup |
| `STORAGE_BACKEND` | Terraform env | `gcs` — use Cloud Storage for receipts |
| `GCS_BUCKET_NAME` | Terraform env | Auto-set from Terraform bucket resource |
| `INSTANCE_CONNECTION_NAME` | Terraform env | Cloud SQL Unix socket path |
| `DB_USER` | Terraform env | `app` |
| `DB_NAME` | Terraform env | `check_splitter` |
| `DB_PASS` | Secret Manager | Auto-generated 32-char password |
| `GEMINI_API_KEY` | Secret Manager | Your Gemini API key |
| `SECRET_KEY` | Secret Manager | Auto-generated 64-char key |
| `LOG_FORMAT` | Terraform env | `json` — structured logging for Cloud Logging |
| `LOG_LEVEL` | Terraform env | `INFO` (configurable via `terraform.tfvars`) |
| `CORS_ORIGINS` | Terraform env | `*` by default — restrict to your domain |

## Updating the Application

```bash
# 1. Make code changes locally

# 2. Build new image
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/check-splitter/app:latest \
  --project PROJECT_ID \
  --region REGION

# 3. Redeploy (forces new revision with latest image)
gcloud run deploy check-splitter \
  --image REGION-docker.pkg.dev/PROJECT_ID/check-splitter/app:latest \
  --region REGION --project PROJECT_ID

# Or via Terraform:
cd terraform && terraform apply
```

## CI/CD with Cloud Build

A `cloudbuild.yaml` is included for automated builds. To set up:

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Create a trigger for your repo (push to `main`)
3. Set substitution variables:
   - `_REGION`: your region (e.g., `europe-west1`)
   - `_SERVICE_NAME`: `check-splitter`
   - `_AR_REPO`: `check-splitter`

The pipeline builds the image, pushes to Artifact Registry, and deploys to Cloud Run.

## Cost Optimization

With the default configuration (`min_instances=0`, `db-f1-micro`):

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| Cloud Run (scale-to-zero) | ~$0 when idle, ~$5–15 with traffic |
| Cloud SQL (db-f1-micro) | ~$7–10 |
| GCS Bucket | < $1 |
| VPC Connector (2× e2-micro) | ~$14 |
| Secret Manager | < $1 |
| **Total** | **~$22–27/month** |

**To minimize costs:**
- Use `min_instances = 0` (cold starts ~2–5s but no idle cost)
- `db-f1-micro` is sufficient for low traffic
- GCS lifecycle deletes receipts after 30 days
- Consider shutting down when not in use: `gcloud sql instances patch INSTANCE --activation-policy=NEVER`

## Troubleshooting

### View Logs
```bash
# Cloud Run logs (recent)
gcloud logging read \
  'resource.type="cloud_run_revision" resource.labels.service_name="check-splitter" severity>=WARNING' \
  --project PROJECT_ID --limit 20 --freshness 10m

# Or use the Console:
# https://console.cloud.google.com/run/detail/REGION/check-splitter/logs
```

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Startup probe failed | Migration error or bad config | Check logs for traceback; common: Alembic multiple heads |
| `can't subtract offset-naive and offset-aware datetimes` | DateTime columns missing `timezone=True` | Migration `a3f1b2c4d5e6` fixes this; ensure it ran |
| `Multiple head revisions` | Alembic migration chain broken | Run `alembic heads` locally; ensure single linear chain |
| `PORT` env var error | Cloud Run reserves PORT | Don't set PORT in Terraform; it's auto-set from `container_port` |
| Cloud SQL not connecting | VPC peering not ready | Terraform `depends_on` for `private_vpc` resolves this |
| `instanceAlreadyExists` | Terraform state lost during slow creation | `terraform import google_sql_database_instance.main projects/PROJECT/instances/NAME` |
| CORS error in browser | `CORS_ORIGINS` not set | Update `cors_origins` in `terraform.tfvars` to include your domain |
| 500 on API calls, health OK | DB tables exist but wrong schema | Check if latest migration ran; may need to drop & recreate DB |

### Reset Database (Nuclear Option)

If the database schema is broken beyond repair:

```bash
# Scale down to release connections
gcloud run services update check-splitter --no-traffic --region REGION

# Drop and recreate
gcloud sql databases delete check_splitter --instance=INSTANCE_NAME --quiet
gcloud sql databases create check_splitter --instance=INSTANCE_NAME

# Rebuild & redeploy (entrypoint will detect fresh DB and create tables)
gcloud builds submit --tag ...
gcloud run deploy check-splitter --image ... --region REGION
```

## Tear Down

```bash
cd terraform

# Disable deletion protection first (if enabled)
# Edit terraform.tfvars: deletion_protection = false
# terraform apply

# Destroy everything
terraform destroy
```

This removes all GCP resources. Data in Cloud SQL and GCS will be permanently deleted.

## File Reference

| File | Purpose |
|------|---------|
| `terraform/main.tf` | All GCP resource definitions |
| `terraform/variables.tf` | Input variable declarations with defaults |
| `terraform/outputs.tf` | Output values (URLs, names, emails) |
| `terraform/terraform.tfvars.example` | Template for your variables |
| `terraform/.gitignore` | Ignores state, lock, and tfvars |
| `cloudbuild.yaml` | CI/CD pipeline definition |
| `Dockerfile` | Multi-stage Python 3.11 container |
| `entrypoint.sh` | Startup script: migrations + gunicorn |
| `Makefile` | Convenience targets (`make tf-apply`, `make deploy`) |
