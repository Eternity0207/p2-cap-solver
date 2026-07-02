# Deployment Guide

## VPS / Virtual Machine Deployment

### Recommended Specs

| Parallel Jobs | RAM | CPU |
|---------------|-----|-----|
| 1–2 | 2 GB | 2 vCPU |
| 3–5 | 4 GB | 4 vCPU |
| 5–10 | 8 GB | 8 vCPU |

### Docker Deployment (Recommended)

```bash
# On your VPS
git clone <repo-url> /opt/cap-solver
cd /opt/cap-solver

cp .env.example .env
nano .env  # Set CAPSOLVER_API_KEY

# Install extensions (see INSTALL.md)
./scripts/setup-extensions.sh

# Deploy
chmod +x deploy.sh
./deploy.sh docker

# Verify
curl http://localhost:8080/api/v1/health
docker compose logs -f
```

### Native Deployment (systemd)

```bash
./deploy.sh setup

# Create systemd service
sudo tee /etc/systemd/system/cap-solver.service << 'EOF'
[Unit]
Description=Cap-Solver Browser Automation
After=network.target

[Service]
Type=simple
User=cap-solver
WorkingDirectory=/opt/cap-solver
Environment=DISPLAY=:99
EnvironmentFile=/opt/cap-solver/.env
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1280x720x24 -ac
ExecStart=/opt/cap-solver/.venv/bin/cap-solver --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cap-solver
```

### Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name capsolver.example.com;

    ssl_certificate /etc/letsencrypt/live/capsolver.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/capsolver.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

## Platform-Specific Notes

### Ubuntu / Debian

```bash
./deploy.sh deps   # Install system packages only
./deploy.sh docker # Or native
```

Xvfb starts automatically in Docker. For native, `deploy.sh` handles it.

### Arch Linux

```bash
./deploy.sh native
# Uses pacman packages: xorg-server-xvfb, nss, gtk3, etc.
```

### Windows

```bash
# In PowerShell or Git Bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
playwright install chromium
cap-solver
```

Set `browser.headless: false` in config if extensions have issues in headless mode.

## Docker Compose Reference

```yaml
# docker-compose.yml
services:
  cap-solver:
    build: .
    ports:
      - "8080:8080"
    environment:
      - CAPSOLVER_API_KEY=${CAPSOLVER_API_KEY}
    volumes:
      - ./data:/app/data
      - ./extensions/nopecha:/app/extensions/nopecha:ro
      - ./extensions/discord-token-login:/app/extensions/discord-token-login:ro
    shm_size: "1gb"  # Important for Chromium
```

### Memory Optimization

```yaml
# config/local.yaml
browser:
  max_concurrent: 2  # Reduce for low-memory VPS
  args:
    - "--disable-dev-shm-usage"
    - "--disable-gpu"
    - "--single-process"  # Use only if desperate (less stable)
```

## Updating

```bash
cd /opt/cap-solver
git pull
docker compose build --no-cache
docker compose up -d
```

## Monitoring

```bash
# Stats endpoint
curl -H "X-API-Key: $KEY" http://localhost:8080/api/v1/stats

# Live stats WebSocket
wscat -c ws://localhost:8080/api/v1/ws/stats

# Logs
tail -f data/logs/cap-solver.log
docker compose logs -f cap-solver
```

## Backup

Important directories:
- `data/jobs.db` — Job history
- `data/artifacts/` — Screenshots and reports
- `config/local.yaml` — Configuration
- `.env` — Secrets

```bash
tar czf cap-solver-backup.tar.gz data/ config/local.yaml .env
```

## Cleanup

```bash
# Delete old completed jobs (via API)
curl -X POST -H "X-API-Key: $KEY" http://localhost:8080/api/v1/admin/cleanup

# Manual cleanup
rm -rf data/browser_profiles/*
```
