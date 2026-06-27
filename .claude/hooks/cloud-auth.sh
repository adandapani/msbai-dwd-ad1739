#!/bin/bash
# Decrypt and activate GCP credentials at session start

set -e

REPO_DIR="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || pwd)"
USER_EMAIL=$(git config user.email 2>/dev/null || echo "noreply@anthropic.com")
ENC_FILE="$REPO_DIR/.cloud-credentials.${USER_EMAIL}.enc"
KEY="${GCP_CREDENTIALS_KEY:-$CLOUD_CREDENTIALS_KEY}"

if [ -z "$KEY" ]; then
  echo "[cloud-auth] No credentials key found (GCP_CREDENTIALS_KEY or CLOUD_CREDENTIALS_KEY). Skipping GCP auth."
  exit 0
fi

if [ ! -f "$ENC_FILE" ]; then
  echo "[cloud-auth] No encrypted credentials file found at $ENC_FILE. Skipping."
  exit 0
fi

echo "[cloud-auth] Decrypting GCP credentials for $USER_EMAIL..."
echo "$KEY" | openssl enc -aes-256-cbc -pbkdf2 -d -pass stdin \
  -in "$ENC_FILE" -out /tmp/credentials.json 2>/dev/null

export GOOGLE_APPLICATION_CREDENTIALS=/tmp/credentials.json
echo "[cloud-auth] GCP credentials activated. Project: proud-sweep-323918"
