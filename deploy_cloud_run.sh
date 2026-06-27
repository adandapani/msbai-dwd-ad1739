#!/bin/bash
# Deploy FIFA dashboard to Google Cloud Run
# Run this locally: bash deploy_cloud_run.sh

set -e

PROJECT_ID="proud-sweep-323918"
SERVICE_NAME="fifa-dashboard"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "==> Building and pushing Docker image..."
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID"

echo "==> Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --service-account "fifa-dashboard-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --project "$PROJECT_ID"

echo ""
echo "==> Dashboard URL:"
gcloud run services describe "$SERVICE_NAME" \
  --platform managed --region "$REGION" \
  --format "value(status.url)" --project "$PROJECT_ID"
