# Deploy

## Docker (recommended)

```bash
cp .env.example .env
# edit CAPSOLVER_API_KEY and NOPECHA_API_KEY

docker compose up -d --build
docker compose logs -f
```

## VPS (bare metal)

```bash
# Install Node 20+
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs xvfb

git clone <repo> /opt/cap-solver
cd /opt/cap-solver
npm ci
cp .env.example .env
# edit .env

# systemd unit
sudo tee /etc/systemd/system/cap-solver.service <<'EOF'
[Unit]
Description=Cap-Solver
After=network.target

[Service]
Type=simple
User=cap-solver
WorkingDirectory=/opt/cap-solver
Environment=DISPLAY=:99
EnvironmentFile=/opt/cap-solver/.env
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1280x720x24 -ac &
ExecStart=/usr/bin/node src/index.js --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now cap-solver
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `CAPSOLVER_API_KEY` | API auth key |
| `NOPECHA_API_KEY` | NopeCHA captcha key |
| `CAPSOLVER_BASE_DIR` | Project root (default `.`) |
| `DISPLAY` | X11 display (`:99` for Xvfb) |

## Resource limits

- `browser.max_concurrent: 1` when using `shared_profile: true`
- Docker: `shm_size: 1gb` minimum for Chromium
- RAM: 1–4 GB per concurrent browser
