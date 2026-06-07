#!/usr/bin/env bash
set -euo pipefail

KNOWLEDGE_BASE_HOST_DIR="${1:-${KNOWLEDGE_BASE_HOST_DIR:-/data/paper-agent/knowledge_base}}"

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

echo "Creating knowledge base directory: ${KNOWLEDGE_BASE_HOST_DIR}"
run_as_root mkdir -p "${KNOWLEDGE_BASE_HOST_DIR}"
run_as_root chown -R "$(id -u):$(id -g)" "${KNOWLEDGE_BASE_HOST_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker first, then run docker compose up -d --build."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is available."
else
  echo "Docker Compose plugin is not available. Install it before deployment."
  exit 1
fi

echo "Server data directory is ready."
echo "Next: copy deploy/.env.example to deploy/.env and replace YOUR_SERVER_IP."
