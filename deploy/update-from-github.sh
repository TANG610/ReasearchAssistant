#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ ! -d ".git" ]; then
  echo "This directory is not a git repository: ${PROJECT_DIR}"
  echo "Clone the GitHub repository to the server first, then run this script."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Neither docker compose nor docker-compose is available."
  exit 1
fi

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
if [ "${branch}" = "HEAD" ]; then
  branch="main"
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "The server working tree has local changes. Commit, stash, or remove them before updating."
  git status --short
  exit 1
fi

if [ "${DEPLOY_BACKUP:-0}" = "1" ]; then
  echo "Running backup before update..."
  bash "${SCRIPT_DIR}/backup.sh"
fi

echo "Fetching latest code from origin/${branch}..."
git fetch --prune origin "${branch}"
git pull --ff-only origin "${branch}"

echo "Rebuilding and restarting services..."
cd "${SCRIPT_DIR}"
"${compose_cmd[@]}" up -d --build --remove-orphans
"${compose_cmd[@]}" ps

echo "Update finished."
