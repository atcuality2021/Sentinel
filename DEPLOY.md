# Sentinel — GCP Ubuntu Server Deployment Guide

Complete setup for `sentinel.atcuality.com` on a GCP Ubuntu VM.

---

## 1. GCP VM — Create Instance

In the GCP Console → Compute Engine → VM Instances → **Create Instance**:

| Setting | Value |
|---|---|
| Machine type | `e2-standard-4` (4 vCPU, 16 GB) — minimum; `e2-standard-8` recommended for heavy use |
| Boot disk | Ubuntu 22.04 LTS, 50 GB SSD |
| Firewall | Allow HTTP (80) + HTTPS (443) |
| Region | Choose closest to your users (e.g. `asia-south1` for India) |

After creation, note the **External IP** — you'll set DNS to this.

SSH in:
```bash
gcloud compute ssh sentinel-vm --zone=YOUR_ZONE
```

---

## 2. System Dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.11 + build tools
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip \
    build-essential git curl wget nginx certbot python3-certbot-nginx \
    sqlite3 ufw

# Verify Python
python3.11 --version   # Python 3.11.x
```

---

## 3. Clone the Repository

```bash
cd /opt
sudo mkdir sentinel && sudo chown $USER:$USER sentinel
cd sentinel

git clone git@github.com:atcuality2021/Sentinel.git .
# OR with HTTPS:
git clone https://github.com/atcuality2021/Sentinel.git .
```

---

## 4. Python Virtual Environment + Install

```bash
cd /opt/sentinel
python3.11 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install .
# For dev/testing tools:
# pip install ".[dev]"
```

---

## 5. Environment Variables (.env)

```bash
cp .env.example .env
nano .env
```

Fill in your secrets:

```bash
# REQUIRED — Gemini for grounding + fallback reasoning
GOOGLE_API_KEY=AIza...

# REQUIRED — vLLM / on-prem model server (your Gemma endpoint)
VLLM_API_KEY=your-key-here

# Optional search enrichment
BRAVE_API_KEY=
SERPAPI_API_KEY=

# KB embedding + reranker (leave defaults if using atcuality.com endpoints)
EMBED_API_BASE=https://embed.atcuality.com/v1
EMBED_MODEL=Qwen3-VL-Embedding-2B
RERANK_API_BASE=https://rerank.atcuality.com/v1
```

Lock permissions so the key file isn't world-readable:
```bash
chmod 600 .env
```

---

## 6. Runtime Config (sentinel.config.yaml)

On first boot the UI at `/settings` creates this file. For headless/automated startup, seed it manually:

```bash
cat > sentinel.config.yaml << 'EOF'
backend: vllm
vllm_model: gemma-4-12b-it
vllm_api_base: https://gemma.atcuality.com/v1
vllm_reasoning_model: gemma-4-27b-it
vllm_reasoning_api_base: https://omni.atcuality.com/v1
gemini_model: gemini-2.5-flash
default_autonomy: propose
search_provider: gemini
search_results: 8
embed_model: Qwen3-VL-Embedding-2B
EOF
```

> After first boot, edit settings at `https://sentinel.atcuality.com/settings` — the YAML is the live config.

---

## 7. Data Directory (SQLite + ChromaDB)

```bash
mkdir -p /opt/sentinel/data
chmod 750 /opt/sentinel/data
# SQLite DB and ChromaDB vector store are auto-created here on first run.
# Back up /opt/sentinel/data/ to keep all projects, tasks, and KB embeddings.
```

Set the data path in `.env` (optional — defaults to `./data`):
```bash
echo "SENTINEL_DATA_DIR=/opt/sentinel/data" >> .env
```

---

## 8. Systemd Service

Create the service unit:
```bash
sudo nano /etc/systemd/system/sentinel.service
```

Paste:
```ini
[Unit]
Description=Sentinel Sovereign Intelligence Agent
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/sentinel
EnvironmentFile=/opt/sentinel/.env
Environment="PYTHONPATH=/opt/sentinel/src"
ExecStart=/opt/sentinel/.venv/bin/uvicorn sentinel.web.app:app \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 2 \
    --log-level info
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sentinel

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sentinel
sudo systemctl start sentinel
sudo systemctl status sentinel
```

Check logs:
```bash
journalctl -u sentinel -f
```

---

## 9. Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/sentinel
```

Paste:
```nginx
server {
    listen 80;
    server_name sentinel.atcuality.com;

    # Will be replaced by certbot with HTTPS redirect
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Long timeout for research runs (synchronous, 5-8 min)
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 30s;

        # SSE streaming (agent timeline)
        proxy_buffering off;
        proxy_cache off;
    }

    # Max upload size for KB file uploads
    client_max_body_size 50M;
}
```

Enable and test:
```bash
sudo ln -s /etc/nginx/sites-available/sentinel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 10. DNS — Point Domain to GCP VM

In your DNS provider (for `atcuality.com`):

| Type | Name | Value | TTL |
|---|---|---|---|
| A | sentinel | `YOUR_GCP_EXTERNAL_IP` | 300 |

Wait for propagation (~5 min for short TTL):
```bash
dig sentinel.atcuality.com +short   # should return your GCP IP
```

---

## 11. SSL — Let's Encrypt

Once DNS propagates:
```bash
sudo certbot --nginx -d sentinel.atcuality.com \
    --non-interactive --agree-tos -m code@atcuality.com
```

Certbot auto-modifies the nginx config to add HTTPS + redirect. Verify:
```bash
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w "%{http_code}" https://sentinel.atcuality.com/projects
# Expected: 200
```

Auto-renewal is set up by certbot automatically via a systemd timer:
```bash
sudo systemctl status certbot.timer
```

---

## 12. Firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
sudo ufw status
```

> Do **not** open port 8080 to the public — uvicorn binds to `127.0.0.1` only. All traffic goes through nginx.

---

## 13. GCP Firewall Rules (if UFW not enough)

In GCP Console → VPC Network → Firewall:
- Allow TCP 80, 443 from `0.0.0.0/0` (ingress, already set if you checked HTTP/HTTPS at VM creation)
- Block port 8080 from outside (uvicorn is internal only)

---

## 14. Verify Full Stack

```bash
# Service running?
sudo systemctl status sentinel

# App responding locally?
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/projects

# HTTPS via nginx?
curl -s -o /dev/null -w "%{http_code}" https://sentinel.atcuality.com/projects

# Logs (live)
journalctl -u sentinel -f
```

Open `https://sentinel.atcuality.com` in a browser — you should see the Sentinel projects page.

---

## 15. Post-Deploy: Settings UI

Go to `https://sentinel.atcuality.com/settings` and configure:

- **Backend** — `vllm` (on-prem Gemma) or `gemini` (cloud fallback)
- **vLLM endpoint** — your Gemma 12B / 27B API base URLs
- **Search provider** — DDG (keyless), Brave, or Gemini grounding
- **Prompts** — customize the 49 built-in prompts at `/settings/prompts`

These write to `sentinel.config.yaml` on the server — no restart needed.

---

## 16. Updates — Pull New Code

```bash
cd /opt/sentinel
source .venv/bin/activate
git pull origin main
pip install .   # pick up any new dependencies
sudo systemctl restart sentinel
```

---

## 17. Backup

The only stateful directory is `/opt/sentinel/data/`:
```bash
# Manual backup
tar czf sentinel-data-$(date +%Y%m%d).tar.gz /opt/sentinel/data/

# Automated daily backup to GCS
# gcloud storage cp /opt/sentinel/data/ gs://your-bucket/sentinel-backups/ --recursive
```

---

## 18. Optional — Docker Deployment

A `Dockerfile` is included for containerised deployment:

```bash
# Build
docker build -t sentinel-agent .

# Run (mount data dir + inject .env)
docker run -d \
    --name sentinel \
    -p 8080:8080 \
    --env-file .env \
    -v /opt/sentinel/data:/app/data \
    -e SENTINEL_DATA_DIR=/app/data \
    --restart unless-stopped \
    sentinel-agent
```

For Cloud Run, see `deploy/cloudrun.sh`.

---

## Quick Reference

| What | Where |
|---|---|
| App | `https://sentinel.atcuality.com` |
| Settings | `https://sentinel.atcuality.com/settings` |
| Logs | `journalctl -u sentinel -f` |
| Config | `/opt/sentinel/sentinel.config.yaml` |
| Secrets | `/opt/sentinel/.env` |
| Database | `/opt/sentinel/data/sentinel.db` |
| Vector store | `/opt/sentinel/data/chroma/` |
| Service | `sudo systemctl restart sentinel` |

---

## Troubleshooting

**502 Bad Gateway** — uvicorn crashed; check `journalctl -u sentinel -n 50`

**504 Gateway Timeout** — research run exceeded nginx timeout; verify `proxy_read_timeout 600s` in nginx config

**`ModuleNotFoundError: sentinel`** — PYTHONPATH not set; verify `Environment="PYTHONPATH=/opt/sentinel/src"` in the systemd unit

**ChromaDB `readonly` error** — `/opt/sentinel/data/` ownership wrong; run `sudo chown -R ubuntu:ubuntu /opt/sentinel/data/`

**SSL renewal fails** — port 80 must be open for ACME challenge; verify `sudo ufw allow 'Nginx Full'`
