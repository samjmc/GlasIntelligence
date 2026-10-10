#!/usr/bin/env bash
# Deploy or update Glas Intelligence on the server: pull main, rebuild, restart, check.
#   ssh root@<server> /opt/glas/deploy/deploy.sh            # deploy origin/main
#   ssh root@<server> /opt/glas/deploy/deploy.sh <git-ref>  # deploy a branch, tag or commit
# Data lives in Docker volumes (uploads, Neo4j, Redis, certificates); a rebuild keeps it.
set -euo pipefail

# This script checks out new code, which can rewrite this very file mid-run; run a copy.
if [ "${GLAS_DEPLOY_COPY:-}" != 1 ]; then
  tmp="$(mktemp /tmp/glas-deploy.XXXXXX.sh)"
  cp "$0" "$tmp"
  GLAS_DEPLOY_COPY=1 exec bash "$tmp" "$@"
fi

DIR=/opt/glas
REF="${1:-origin/main}"
cd "$DIR"

SECRETS="$DIR/deploy/app-secrets.conf"
[ -f "$SECRETS" ] || { echo "missing $SECRETS: run deploy/bootstrap-server.sh first"; exit 1; }
missing=$(grep -E '^(APP_DOMAIN|ACME_EMAIL|SECRET_KEY|NEO4J_AUTH|LLM_API_KEY|SUPABASE_URL|SUPABASE_SERVICE_KEY|SUPABASE_JWT_SECRET|VITE_SUPABASE_URL|VITE_SUPABASE_ANON_KEY)=$' "$SECRETS" | cut -d= -f1 || true)
[ -z "$missing" ] || { echo "fill these in $SECRETS first:"; echo "$missing"; exit 1; }

echo "== code: $REF"
git fetch --quiet origin
git checkout --quiet --detach "$REF"
git log -1 --format='   %h %s'

# Export the settings so compose can fill ${APP_DOMAIN}, ${ACME_EMAIL} and the build args.
set -a
. "$SECRETS"
set +a

cd deploy
echo "== build"
docker compose build --pull app
echo "== start"
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

echo "== wait for the app (first start downloads models; can take a few minutes)"
for i in $(seq 1 60); do
  if curl -fsS "https://${APP_DOMAIN}/health" >/dev/null 2>&1; then
    echo "   OK: https://${APP_DOMAIN}/health answers"
    docker compose ps --format 'table {{.Service}}\t{{.Status}}'
    exit 0
  fi
  sleep 10
done
echo "FAILED: https://${APP_DOMAIN}/health did not answer in 10 minutes"
docker compose ps
docker compose logs --tail 40 app caddy
exit 1
