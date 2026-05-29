#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-qsim-playground-prod}"
REGION="${REGION:-asia-south1}"
SERVICE_NAME="${SERVICE_NAME:-qsim-backend}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-https://qsim-playground.vercel.app}"

gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

gcloud run deploy "${SERVICE_NAME}" \
  --source ./backend \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 20 \
  --timeout 300 \
  --set-secrets GEMINI_API_KEYS=GEMINI_API_KEYS:latest,SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_ANON_KEY=SUPABASE_ANON_KEY:latest,SUPABASE_SERVICE_ROLE_KEY=SUPABASE_SERVICE_ROLE_KEY:latest,SUPABASE_JWT_SECRET=SUPABASE_JWT_SECRET:latest,SENTRY_DSN=SENTRY_DSN:latest \
  --set-env-vars "ALLOWED_ORIGINS=${FRONTEND_ORIGIN},ENABLE_DEBUG_ROUTES=false"
