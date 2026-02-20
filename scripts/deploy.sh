#!/usr/bin/env bash
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
REMOTE_USER="${REMOTE_USER:?Set REMOTE_USER env var}"
REMOTE_HOST="${REMOTE_HOST:?Set REMOTE_HOST env var}"
REMOTE_DIR="/home/${REMOTE_USER}/superscrape"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== SuperScrape Deploy ==="
echo "  Local:  ${LOCAL_DIR}"
echo "  Remote: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
echo ""

# ── Step 1: Sync files ──────────────────────────────────────────────────────
echo "[1/4] Syncing project files to VPS..."
rsync -avz --delete \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='node_modules/' \
    --exclude='.next/' \
    --exclude='.git/' \
    --exclude='*.pyc' \
    "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# ── Step 2: Sync .env ───────────────────────────────────────────────────────
echo "[2/4] Syncing .env..."
scp "${LOCAL_DIR}/.env" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/.env"

# ── Step 3: Build and start ─────────────────────────────────────────────────
echo "[3/4] Building and starting containers..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "
    cd ${REMOTE_DIR}
    docker compose down || true
    docker compose up --build -d
    echo ''
    echo 'Container status:'
    docker compose ps
"

# ── Step 4: Health check ────────────────────────────────────────────────────
echo "[4/4] Waiting for health check..."
sleep 15

HEALTH=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "curl -sf http://localhost:8001/health 2>/dev/null || echo 'FAIL'")
if [ "${HEALTH}" = '{"status":"ok"}' ]; then
    echo ""
    echo "=== Deploy SUCCESS ==="
    echo "  Backend:  http://${REMOTE_HOST}:8001/health"
    echo "  Frontend: http://${REMOTE_HOST}:3001"
    echo "  Nginx:    http://${REMOTE_HOST}:2088"
else
    echo ""
    echo "=== Health check FAILED ==="
    echo "  Response: ${HEALTH}"
    echo ""
    echo "  Check logs:"
    echo "  ssh ${REMOTE_USER}@${REMOTE_HOST} 'cd ${REMOTE_DIR} && docker compose logs --tail=50'"
    exit 1
fi
