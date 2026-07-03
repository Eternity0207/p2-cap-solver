# Cap-Solver

Node.js + Playwright service for Poketwo verification automation.  
Input is exactly what you asked for: `token` and `link`.

## Run locally

```bash
git clone <your-repo-url>
cd Cap-Solver
npm install
cp .env.example .env
```

Set these in `.env`:

```env
CAPSOLVER_API_KEY=your-api-key
NOPECHA_API_KEY=your-nopecha-key
```

Start server:

```bash
npm start
```

Or with custom host/port:

```bash
node src/index.js --host 0.0.0.0 --port 8080
```

## API Endpoints

- `GET /api/v1/health` — health check
- `POST /api/v1/verify` — submit verification with `token` + `link`
- `POST /api/v1/jobs` — full job API (advanced)
- `GET /api/v1/jobs/{job_id}` — fetch job status/details
- `WS /api/v1/ws/jobs/{job_id}` — live job updates

## Curl Examples

Queue job and return immediately:

```bash
curl -X POST "http://localhost:8080/api/v1/verify" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "token": "YOUR_DISCORD_TOKEN",
    "link": "https://verify.poketwo.net/captcha/1519215866414239746"
  }'
```

Wait up to 600 seconds in one request:

```bash
curl -X POST "http://localhost:8080/api/v1/verify?wait=600" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "token": "YOUR_DISCORD_TOKEN",
    "link": "https://verify.poketwo.net/captcha/1519215866414239746"
  }'
```

## Stack

- **Runtime:** Node.js 20+
- **Browser:** Playwright (Chromium / Brave / Chrome)
- **HTTP:** Express
- **Jobs:** SQLite via sql.js

## Notes

- Extensions can be placed in `extensions/nopecha` and `extensions/discord-token-login`, or auto-downloaded from the Chrome Web Store.
- Keep Brave/Chrome installed on the host for best Cloudflare bypass.
- For Linux servers without a display, Xvfb is auto-used when available (`browser.headless` must stay `false`).
