#!/usr/bin/env bash
# Deploy Sentinel to Google Cloud Run from source (Cloud Build does the container build —
# no local Docker required). Judges get a public HTTPS URL = the "live testing access"
# submission artifact.
#
# Prereqs (one-time):
#   gcloud auth login
#   gcloud config set project <YOUR_PROJECT_ID>
#   gcloud services enable run.googleapis.com cloudbuild.googleapis.com
#
# Usage:
#   GOOGLE_API_KEY=AIza... ./deploy/cloudrun.sh
#
# Override any of these via env:
#   SERVICE   (default: sentinel)
#   REGION    (default: asia-south1  — APAC; use asia-southeast1 for Singapore)
#   PROJECT   (default: current gcloud project)
set -euo pipefail

SERVICE="${SERVICE:-sentinel}"
REGION="${REGION:-asia-south1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "ERROR: no GCP project set. Run: gcloud config set project <YOUR_PROJECT_ID>" >&2
  exit 1
fi

if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "ERROR: GOOGLE_API_KEY is not set. Get one at https://aistudio.google.com/apikey" >&2
  echo "Then run: GOOGLE_API_KEY=AIza... ./deploy/cloudrun.sh" >&2
  exit 1
fi

echo "Deploying '${SERVICE}' to Cloud Run [project=${PROJECT} region=${REGION}] ..."

# --allow-unauthenticated: judges/evaluators can open the URL without a Google login.
# Env vars configure the LLM gateway for the cloud demo (Gemini via AI Studio key).
gcloud run deploy "${SERVICE}" \
  --source . \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 4 \
  --set-env-vars "SENTINEL_LLM_BACKEND=gemini,GOOGLE_GENAI_USE_VERTEXAI=FALSE,GOOGLE_API_KEY=${GOOGLE_API_KEY},SENTINEL_GEMINI_MODEL=${SENTINEL_GEMINI_MODEL:-gemini-2.5-flash}"

URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format 'value(status.url)')"
echo
echo "✅ Deployed. Live URL (put this in your submission):"
echo "   ${URL}"
echo "   Health: ${URL}/healthz"
