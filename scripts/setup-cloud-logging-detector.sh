#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
TOPIC="${PUBSUB_TOPIC:-sentinelops-incoming-events}"
SINK_NAME="${SENTINELOPS_LOG_SINK:-sentinelops-demo-api-errors}"
SERVICE_NAME="${SENTINELOPS_DETECT_SERVICE:-demo-api}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "GOOGLE_CLOUD_PROJECT or an active gcloud project is required" >&2
  exit 1
fi

DESTINATION="pubsub.googleapis.com/projects/${PROJECT_ID}/topics/${TOPIC}"
LOG_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE_NAME}\" AND httpRequest.status>=500"

if gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud logging sinks update "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --description="Route ${SERVICE_NAME} Cloud Run 5xx request logs into SentinelOps detection"
else
  gcloud logging sinks create "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --description="Route ${SERVICE_NAME} Cloud Run 5xx request logs into SentinelOps detection"
fi

WRITER_IDENTITY="$(gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" --format='value(writerIdentity)')"
if [[ -z "${WRITER_IDENTITY}" ]]; then
  echo "Cloud Logging sink writer identity was not returned" >&2
  exit 1
fi

gcloud pubsub topics add-iam-policy-binding "${TOPIC}" \
  --project="${PROJECT_ID}" \
  --member="${WRITER_IDENTITY}" \
  --role="roles/pubsub.publisher" \
  --quiet >/dev/null

echo "Cloud Logging detector configured."
echo "  sink: ${SINK_NAME}"
echo "  service: ${SERVICE_NAME}"
echo "  topic: ${TOPIC}"
echo "  writer: ${WRITER_IDENTITY}"
echo "  filter: ${LOG_FILTER}"
