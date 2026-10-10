# Hosting: one Hetzner server

Glas Intelligence runs on **one Hetzner cloud server** with Docker Compose. Decided 2026-10-05.

| Part | What runs | Notes |
|---|---|---|
| `caddy` | public HTTPS for **app.glasinsight.com** | Let's Encrypt certificate, renewed automatically |
| `app` | the built frontend (nginx) + the Flask API (gunicorn, one process) | `Dockerfile.prod` |
| `worker` | Celery worker for deep research and scenario bundles | same image as `app` |
| `neo4j` | Neo4j Community 5.26, the knowledge graph | not reachable from outside |
| `redis` | Celery broker | not reachable from outside |

Login and billing stay on **Supabase** (cloud). LLM calls go to **DeepSeek**. **glasinsight.com** stays the static interview demo on Cloudflare Pages; the app lives on the **app.** subdomain.

All files are in `deploy/`: `docker-compose.yml`, `Caddyfile`, `nginx-app.conf`, `bootstrap-server.sh`, `deploy.sh`, `push-secrets.ps1`, and `app-secrets.example.conf`.

## Cost (Hetzner prices from 15 June 2026, excl. VAT)

| Item | € / month |
|---|---|
| CX33 server (4 vCPU, 8 GB RAM, 80 GB disk), Germany or Finland | about 8.49 |
| IPv4 address | about 0.60 |
| Daily backups (20% of the server price, 7 kept) | about 1.70 |
| **Total** | **about 10.80** (about 13.30 with Irish VAT) |

Plus LLM tokens: about $0.15 per graph build, more per simulation and report.

The kit is sized for 8 GB: Neo4j gets a 1 GB heap and a 512 MB page cache, and the 4 GB swap file covers peaks. The only local model is the small embedder (`BAAI/bge-small-en-v1.5`); the agents' LLM calls go to the API. That is enough for a few people at a time. CX43 (16 GB) was the first choice but was sold out on 2026-10-10. To grow, resize the server in the Hetzner console (a few minutes, data kept), then raise the Neo4j memory lines in `docker-compose.yml` and run `deploy.sh`.

## First setup

Steps marked **(you)** need your accounts or payment. Claude must not create accounts, pay, or handle secret values.

1. **(you) Hetzner account and project.** Go to <https://console.hetzner.cloud> and create a project called `glas`.
2. **(you) SSH key.** In the project, open *Security → SSH keys → Add* and paste the public key from `%USERPROFILE%\.ssh\glas_hetzner.pub`. Its private half never leaves your PC.
3. **(you) Server.** Choose *Add server*:
   - Location: Nuremberg or Falkenstein (DE), or Helsinki (FI).
   - Image: **Ubuntu 24.04** or **26.04** (Docker supports both).
   - Type: shared vCPU, x86, **CX33** or bigger.
   - Networking: IPv4 and IPv6.
   - SSH key: `glas_hetzner`.
   - Turn **Backups** on.
   - Name: `glas-prod`.
   Note the IPv4 address.
4. **(you) DNS.** In Cloudflare, for glasinsight.com, add a record: `A`, name `app`, content = the server's IPv4, **Proxy status: DNS only (grey cloud)**. Optionally add an `AAAA` record for the IPv6. "DNS only" lets Caddy get its own certificate directly. Proxying through Cloudflare can be switched on later, with SSL mode *Full (strict)*.
5. **(you) Supabase.** In *Authentication → URL Configuration*, add `https://app.glasinsight.com` as a redirect URL. Set it as the Site URL if this is now the main app.
6. **Bootstrap the server** (Claude can do this over SSH, or you can):
   ```
   ssh -i %USERPROFILE%\.ssh\glas_hetzner root@<IPv4>
   curl -fsSL https://raw.githubusercontent.com/samjmc/GlasIntelligence/main/deploy/bootstrap-server.sh | bash
   ```
   It does the following:
   - installs updates, automatic security updates, a firewall (22, 80, 443 only), a 4 GB swap file and Docker;
   - clones the repo to `/opt/glas`;
   - creates `/opt/glas/deploy/app-secrets.conf` (chmod 600), with a generated `SECRET_KEY` and Neo4j password. It never prints them.
7. **(you) Secrets.** On your PC, in your own PowerShell window:
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\push-secrets.ps1 -Server <IPv4>
   ```
   For each value it uses your user environment variable when one exists (`LLM_API_KEY`, …); otherwise it asks, with hidden typing. Nothing is printed, and the temporary files are deleted at both ends.
8. **Deploy:**
   ```
   ssh -i %USERPROFILE%\.ssh\glas_hetzner root@<IPv4> /opt/glas/deploy/deploy.sh
   ```
   It builds the image on the server (about 10–15 minutes the first time) and starts the stack. It waits until `https://app.glasinsight.com/health` answers, and stops with the logs if it does not.
9. **Check by hand:** open <https://app.glasinsight.com>, sign in, and run one small simulation end to end.

## Everyday operations

| Task | Command (run on the server, or through `ssh … root@<IPv4> '<command>'`) |
|---|---|
| Deploy the latest `main` | `/opt/glas/deploy/deploy.sh` |
| Deploy a branch, tag or commit | `/opt/glas/deploy/deploy.sh <ref>` |
| Roll back | `/opt/glas/deploy/deploy.sh <previous commit sha>` |
| Status | `cd /opt/glas/deploy && docker compose ps` |
| Logs | `cd /opt/glas/deploy && docker compose logs -f --tail 100 app worker` |
| Restart one part | `cd /opt/glas/deploy && docker compose restart app` |
| Change a setting | edit `/opt/glas/deploy/app-secrets.conf` (or re-run `push-secrets.ps1`), then `deploy.sh` |
| Neo4j browser | `ssh -L 7474:localhost:7474 …`, then open <http://localhost:7474> (port 7474 is not published; add it to the compose file first if needed) |

**Data:**
- Projects, simulations and the graph snapshot cache are in the `uploads` volume.
- The graph is in `neo4j_data`.
- Downloaded models are in `hf_cache`.
- The HTTPS certificates are in `caddy_data`.

`deploy.sh` rebuilds the containers, never the volumes.

**Backups:** Hetzner's daily backups copy the whole disk, including every volume, and keep 7. To restore, use the Hetzner console: *Servers → glas-prod → Backups → Restore*. Neo4j recovers its database from the transaction log on start. Before a risky change, take a manual *Snapshot* in the console as well.

**Updates:**
- Ubuntu security updates install themselves (`unattended-upgrades`).
- `deploy.sh` pulls fresh base images on every build.
- Reboot the server after kernel updates. The stack comes back by itself, because every service has `restart: unless-stopped`.

## Known limits

- **One API process.** Simulation state lives in memory (the gunicorn worker count is 1, with 4 threads). Do not raise the worker count. Scale up with a bigger server, not more processes.
- **Billing needs Supabase.** `/api/simulation/start` takes a credit through Supabase, so the server must have the Supabase settings (they are required in `deploy.sh`).
- **Live graph memory** costs about 4x the graph build in LLM tokens (measured 2026-10-04). It stays off by default.
