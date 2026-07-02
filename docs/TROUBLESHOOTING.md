# Troubleshooting

## Common Issues

### Extensions not loading

**Symptoms:** Captcha never solves, Discord login fails, logs show `extension_not_found`.

**Fix:**
1. Verify `extensions/nopecha/manifest.json` exists
2. Verify `extensions/discord-token-login/manifest.json` exists
3. Extensions must be Manifest V3 (MV2 not supported by Playwright)
4. Use absolute paths in config if running from a different directory

```bash
./scripts/setup-extensions.sh
ls -la extensions/*/manifest.json
```

### Cloudflare stuck on "Performing security verification"

**Symptoms:** Page never loads, browser reloads in a loop, or crashes after clicking verify.

**Root causes (fixed in current version):**
1. Stock Playwright `connect_over_cdp` leaks `Runtime.Enable` — Cloudflare detects automation and reloads
2. Init-script stealth patches applied before CF clears — fingerprint mismatch
3. Multiple browsers sharing one profile — `SingletonLock` crashes
4. Page reload during NopeCHA solve — resets the challenge

**Fix:**
1. Cap-Solver now uses **Patchright** (patched Playwright) with real Brave/Chrome via `launch_persistent_context`
2. Run headed (`browser.headless: false`) — Cloudflare detects headless mode
3. Keep `max_concurrent: 1` when `shared_profile: true`
4. Kill stale processes before retry:
   ```bash
   ./scripts/kill-stale.sh
   ```
5. On desktop Linux, set `DISPLAY=:0` (or your Wayland/X11 display)
6. Do not manually reload the page while NopeCHA is solving

**Config:**
```yaml
browser:
  headless: false
  max_concurrent: 1
  shared_profile: true
automation:
  poketwo:
    cloudflare:
      max_wait_seconds: 240
```

### Captcha timeout

**Symptoms:** Job fails at `waiting_captcha` step.

**Fix:**
1. Ensure NopeCHA extension is installed and has API credits (if required)
2. Increase timeout in config:
   ```yaml
   automation:
     poketwo:
       captcha:
         max_wait_seconds: 180
   ```
3. Try `browser.headless: false` — some extensions struggle in headless mode
4. Check screenshot at `data/artifacts/{job_id}/02_captcha_timeout.png`

### Discord login fails

**Symptoms:** Job fails at `discord_login` step.

**Fix:**
1. Verify Discord token is valid (not expired/revoked)
2. Ensure Discord Token Login extension popup selectors match your extension version
3. Customize selectors in config:
   ```yaml
   automation:
     poketwo:
       discord:
         token_login:
           token_input_selectors:
             - '#token'
             - 'input[type="text"]'
           submit_selectors:
             - 'button:has-text("Login")'
   ```
4. Check `05_login_failed.png` screenshot

### Authorize button not found

**Symptoms:** Warning in logs, job may still succeed if already authorized.

**Fix:**
1. Token may already have authorized the bot — check final screenshot
2. Update authorize selectors for your Discord UI language:
   ```yaml
   automation:
     poketwo:
       discord:
         authorize_button:
           selectors:
             - 'button:has-text("Authorize")'
   ```

### Verification text not detected

**Symptoms:** Job retries but never sees "verified".

**Fix:**
1. Check `07_final.png` screenshot for actual page content
2. Add success text patterns:
   ```yaml
   automation:
     poketwo:
       success:
         text_patterns:
           - "verified"
           - "Verification complete"
           - "success"
   ```

### Browser crashes / OOM on VPS

**Symptoms:** Random failures, `Killed` in logs, high memory usage.

**Fix:**
1. Reduce concurrent jobs:
   ```yaml
   browser:
     max_concurrent: 2
   ```
2. Increase Docker shared memory: `shm_size: "2gb"`
3. Add swap space on VPS
4. Ensure `--disable-dev-shm-usage` is in browser args

### Xvfb / Display errors (Linux)

**Symptoms:** `Missing X server or $DISPLAY`.

**Fix:**
```bash
# Install xvfb
sudo apt-get install xvfb  # Ubuntu/Debian
sudo pacman -S xorg-server-xvfb  # Arch

# Start manually
export DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 -ac &

# Or use Docker (handles Xvfb automatically)
./deploy.sh docker
```

### API returns 401

**Fix:** Set matching API key:
```bash
# .env
CAPSOLVER_API_KEY=your-secret-key

# Request
curl -H "X-API-Key: your-secret-key" ...
```

### Patchright browser not found

```bash
source .venv/bin/activate
pip install -e .
patchright install chromium
# On desktop Linux with Brave installed, Brave is auto-detected (preferred)
# Or install Google Chrome and set browser.executable_path
```

## Debug Mode

Enable verbose console logging:

```yaml
# config/local.yaml
logging:
  level: "DEBUG"
  format: "console"
```

## Log Locations

| Location | Content |
|----------|---------|
| `data/logs/cap-solver.log` | Application logs (JSON) |
| `data/artifacts/{job_id}/` | Screenshots per step |
| `docker compose logs` | Container stdout |

## Getting Help

When reporting issues, include:
1. Job ID and `/api/v1/jobs/{id}/report` output
2. Screenshots from `data/artifacts/{job_id}/`
3. Relevant log lines from `data/logs/cap-solver.log`
4. Platform info from `/api/v1/health`
5. Extension versions (from manifest.json)
