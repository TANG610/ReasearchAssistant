#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

read_env_var() {
  local name="$1"
  local fallback="$2"
  local line value

  if [ -f ".env" ]; then
    line="$(grep -E "^${name}=" ".env" | tail -n 1 || true)"
    if [ -n "${line}" ]; then
      value="${line#*=}"
      value="${value%$'\r'}"
      value="${value%\"}"
      value="${value#\"}"
      value="${value%\'}"
      value="${value#\'}"
      printf '%s' "${value}"
      return
    fi
  fi

  printf '%s' "${fallback}"
}

POSTGRES_DB="${POSTGRES_DB:-$(read_env_var POSTGRES_DB research)}"
POSTGRES_USER="${POSTGRES_USER:-$(read_env_var POSTGRES_USER research)}"
KNOWLEDGE_BASE_HOST_DIR="${KNOWLEDGE_BASE_HOST_DIR:-$(read_env_var KNOWLEDGE_BASE_HOST_DIR /data/paper-agent/knowledge_base)}"

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="${SCRIPT_DIR}/backups/${timestamp}"
mkdir -p "${backup_dir}"

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Neither docker compose nor docker-compose is available."
  exit 1
fi

echo "Backing up Postgres database '${POSTGRES_DB}'..."
"${compose_cmd[@]}" exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${backup_dir}/postgres-${timestamp}.sql"

if [ -d "${KNOWLEDGE_BASE_HOST_DIR}" ]; then
  echo "Backing up knowledge base directory '${KNOWLEDGE_BASE_HOST_DIR}'..."
  parent_dir="$(dirname "${KNOWLEDGE_BASE_HOST_DIR}")"
  base_name="$(basename "${KNOWLEDGE_BASE_HOST_DIR}")"
  tar -czf "${backup_dir}/knowledge-base-${timestamp}.tar.gz" -C "${parent_dir}" "${base_name}"
else
  echo "Knowledge base directory does not exist, skipped: ${KNOWLEDGE_BASE_HOST_DIR}"
fi

echo "Backup written to: ${backup_dir}"
echo "Note: deploy/.env contains secrets and is not copied. Store it securely if needed."
