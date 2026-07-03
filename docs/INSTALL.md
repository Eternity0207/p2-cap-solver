# Install

## Requirements

- Node.js 20+
- Brave or Chrome (recommended for Cloudflare)
- Xvfb on headless Linux servers

## Local setup

```bash
git clone <your-repo-url>
cd Cap-Solver
npm install
cp .env.example .env
```

Edit `.env`:

```env
CAPSOLVER_API_KEY=your-api-key
NOPECHA_API_KEY=your-nopecha-key
```

## Extensions

Place unpacked extensions in:

- `extensions/nopecha/manifest.json`
- `extensions/discord-token-login/manifest.json`

Or let Cap-Solver auto-download them from the Chrome Web Store on first run.

```bash
./scripts/setup-extensions.sh
```

## Run

```bash
npm start
```

Custom port:

```bash
node src/index.js --host 0.0.0.0 --port 8080
```

Install Playwright Chromium only:

```bash
node src/index.js --install-browsers
```

## Docker

```bash
docker compose up -d --build
```

Health check: `curl http://localhost:8080/api/v1/health`
