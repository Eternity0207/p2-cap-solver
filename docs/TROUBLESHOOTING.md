# Troubleshooting

## Extensions not loading

1. Verify `extensions/nopecha/manifest.json` exists
2. Verify `extensions/discord-token-login/manifest.json` exists
3. Extensions must be Manifest V3
4. Run `./scripts/setup-extensions.sh`

## Cloudflare stuck on "Performing security verification"

1. Use **headed** mode (`browser.headless: false`) with Xvfb on servers
2. Keep `max_concurrent: 1` when `shared_profile: true`
3. Kill stale browser processes: `./scripts/kill-stale.sh`
4. Set `DISPLAY=:0` on desktop Linux

## Browser crashes / profile lock

```bash
./scripts/kill-stale.sh
./scripts/clean-data.sh   # optional: wipe profiles
```

## Playwright browser missing

```bash
npx playwright install chromium
# or
node src/index.js --install-browsers
```

## Job timeout

Increase in `config/default.yaml`:

```yaml
browser:
  job_timeout_seconds: 600
automation:
  poketwo:
    captcha:
      max_wait_seconds: 180
    cloudflare:
      max_wait_seconds: 300
```

## API 401

Set `X-API-Key` header to match `CAPSOLVER_API_KEY` in `.env`.
