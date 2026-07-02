# Cap-Solver

FastAPI service for Poketwo verification automation.  
Input is exactly what you asked for: `token` and `link`.

## Run on VPS

```bash
git clone <your-repo-url>
cd Cap-Solver
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set these in `.env`:

```env
CAPSOLVER_API_KEY=your-api-key
NOPECHA_API_KEY=your-nopecha-key
```

Start server:

```bash
.venv/bin/python -m capsolver.main --host 0.0.0.0 --port 8080
```

## FastAPI Endpoints

- `GET /api/v1/health` - health check
- `POST /api/v1/verify` - submit verification with `token` + `link`
- `POST /api/v1/jobs` - full job API (advanced)
- `GET /api/v1/jobs/{job_id}` - fetch job status/details

Swagger UI: `http://<host>:8080/docs`

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

## Notes

- Extensions are fetched from Chrome Web Store each run (no local extension folder required).
- Keep Brave/Chrome installed on the VPS.
- For Linux servers without display, Xvfb is auto-used when available.
