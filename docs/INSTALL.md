# Installation Guide

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 4+ GB (512MB–1GB per parallel browser) |
| Disk | 2 GB | 5+ GB |
| OS | Windows 10+, Ubuntu 20.04+, Debian 11+, Arch Linux |

## Prerequisites

### 1. Python 3.11+

```bash
python3 --version  # Should be 3.11 or higher
```

### 2. Browser Extensions (Required)

Cap-Solver loads two Chrome extensions at runtime:

1. **NopeCHA** — Solves Cloudflare Turnstile captchas automatically
2. **Discord Token Login** — Logs into Discord using a provided token

Run the setup helper:

```bash
chmod +x scripts/setup-extensions.sh
./scripts/setup-extensions.sh
```

Copy unpacked extension folders to:
- `extensions/nopecha/manifest.json` must exist
- `extensions/discord-token-login/manifest.json` must exist

### 3. System Dependencies (Native Install)

The `deploy.sh` script installs these automatically:

**Ubuntu/Debian:**
```bash
sudo apt-get install -y python3 python3-venv xvfb \
  libnss3 libatk-bridge2.0-0 libgbm1 libgtk-3-0 fonts-liberation
```

**Arch Linux:**
```bash
sudo pacman -S python xorg-server-xvfb nss gtk3 ttf-liberation
```

**Windows:**
- Install Python from [python.org](https://python.org)
- No Xvfb needed (native display)

## Installation Methods

### Method 1: One-Command Deploy (Native)

```bash
git clone <repo-url> Cap-Solver && cd Cap-Solver
chmod +x deploy.sh scripts/setup-extensions.sh
./deploy.sh setup     # Install everything
./deploy.sh native    # Start server
```

### Method 2: Docker

```bash
cp .env.example .env
# Configure extensions in extensions/ directories
./deploy.sh docker
```

### Method 3: Manual

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium
playwright install-deps chromium
mkdir -p data/{logs,artifacts,browser_profiles}
cap-solver --install-browsers
cap-solver
```

## Configuration

### Environment Variables

Create `.env` from template:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `CAPSOLVER_API_KEY` | Secret key for API auth (required in production) |
| `CAPSOLVER_BASE_DIR` | Project root directory |
| `CAPSOLVER_BROWSER__MAX_CONCURRENT` | Max parallel jobs (default: 3) |
| `CAPSOLVER_BROWSER__HEADLESS` | `true` or `false` |
| `CAPSOLVER_JOBS__MAX_RETRIES` | Retry count on failure (default: 3) |

### YAML Configuration

Copy and edit local overrides:

```yaml
# config/local.yaml
server:
  api_key: "your-secret-key"
  port: 8080

browser:
  max_concurrent: 5
  headless: true
  job_timeout_seconds: 300

jobs:
  max_retries: 3
  retry_delay_seconds: 5

automation:
  poketwo:
    captcha:
      max_wait_seconds: 120
    success:
      text_patterns:
        - "verified"
        - "successfully verified"
```

### Extension Paths

```yaml
browser:
  extensions:
    nopecha_path: "extensions/nopecha"
    discord_token_path: "extensions/discord-token-login"
```

## Verify Installation

```bash
# Health check
curl http://localhost:8080/api/v1/health

# Expected response:
# {"status":"healthy","version":"1.0.0","platform":{...}}
```

## Post-Install

1. Set a strong `CAPSOLVER_API_KEY` in production
2. Configure a reverse proxy (nginx) with TLS for public access
3. Set `browser.max_concurrent` based on available RAM
4. Monitor logs at `data/logs/cap-solver.log`
