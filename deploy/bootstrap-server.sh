#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server for Glas Intelligence. Run as root:
#
#   curl -fsSL https://raw.githubusercontent.com/samjmc/GlasIntelligence/main/deploy/bootstrap-server.sh | bash
#
# It is safe to run again: every step checks before it changes anything.
# What it does:
#   1. installs security updates, turns on automatic security updates and a firewall (22, 80, 443);
#   2. installs Docker Engine + the compose plugin from Docker's own repository;
#   3. clones the repo to /opt/glas;
#   4. creates deploy/app-secrets.conf (chmod 600) from the template and generates
#      SECRET_KEY and the Neo4j password. It never prints a secret.
# It does NOT start the app: fill the remaining secrets first, then run deploy/deploy.sh.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/samjmc/GlasIntelligence.git}"
DIR=/opt/glas

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || echo "WARNING: written for Ubuntu 24.04/26.04 (this is ${PRETTY_NAME:-unknown})"

echo "== 1/4 updates, automatic security updates, firewall"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null
ufw --force enable >/dev/null
# Swap guards the run-time peaks (torch + OASIS models + Neo4j) against the OOM killer.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 2/4 Docker"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version

echo "== 3/4 code in $DIR"
if [ ! -d "$DIR/.git" ]; then
  git clone --quiet "$REPO_URL" "$DIR"
else
  git -C "$DIR" pull --ff-only --quiet
fi

echo "== 4/4 secrets file"
SECRETS="$DIR/deploy/app-secrets.conf"
if [ ! -f "$SECRETS" ]; then
  install -m 600 /dev/null "$SECRETS"
  cp "$DIR/deploy/app-secrets.example.conf" "$SECRETS"
  chmod 600 "$SECRETS"
fi
set_if_empty() { # key value: fill KEY= only when it has no value yet
  if grep -q "^$1=$" "$SECRETS"; then sed -i "s|^$1=$|$1=$2|" "$SECRETS"; fi
}
set_if_empty SECRET_KEY "$(openssl rand -hex 32)"
set_if_empty NEO4J_PASSWORD "$(openssl rand -hex 24)"
NEO_PW="$(grep '^NEO4J_PASSWORD=' "$SECRETS" | cut -d= -f2-)"
set_if_empty NEO4J_AUTH "neo4j/$NEO_PW"
unset NEO_PW

echo
echo "Done. Still empty in $SECRETS:"
grep -E '^[A-Z_]+=$' "$SECRETS" | cut -d= -f1 | sed 's/^/  /'
echo
echo "Next: fill the required ones (run deploy/push-secrets.ps1 on your PC), then:"
echo "  $DIR/deploy/deploy.sh"
