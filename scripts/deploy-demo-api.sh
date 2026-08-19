#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-sentinelops-505805}"
REGION="${GOOGLE_CLOUD_REGION:-europe-west1}"
SERVICE="${DEMO_SERVICE:-demo-api}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="$ROOT_DIR/demo"

usage() {
  echo "Usage: $0 healthy|broken"
}

MODE="${1:-}"
if [[ "$MODE" != "healthy" && "$MODE" != "broken" ]]; then
  usage
  exit 2
fi

if [[ "$MODE" == "healthy" ]]; then
  VERSION="v1"
  BROKEN="false"
else
  VERSION="v2"
  BROKEN="true"
fi

echo "Deploying $SERVICE $VERSION ($MODE) to $PROJECT_ID/$REGION"
gcloud config set project "$PROJECT_ID" >/dev/null

gcloud run deploy "$SERVICE" \
  --source "$DEMO_DIR" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "DEMO_VERSION=$VERSION,DEMO_BROKEN=$BROKEN" \
  --memory 256Mi \
  --cpu 1 \
  --min 0 \
  --max 1 \
  --concurrency 20 \
  --timeout 30

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
REVISION="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.latestReadyRevisionName)')"

echo "Revision: $REVISION"
echo "URL: $URL"
echo "Health:"
curl -sS -i "$URL/health"
