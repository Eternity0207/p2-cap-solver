# API Reference

Base URL: `http://localhost:8080/api/v1`

## Authentication

When `CAPSOLVER_API_KEY` is set, include the header on all endpoints except `/health`:

```
X-API-Key: your-api-key
```

## Endpoints

### System

#### `GET /health`

Health check (no auth required).

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "platform": {
    "os": "ubuntu",
    "distro": "ubuntu",
    "arch": "x86_64",
    "has_display": true,
    "xvfb_available": true
  }
}
```

#### `GET /stats`

Service statistics.

**Response:**
```json
{
  "queue_size": 2,
  "active_browsers": 1,
  "max_concurrent": 3,
  "jobs_by_status": {
    "completed": 15,
    "failed": 2,
    "running": 1
  },
  "version": "1.0.0"
}
```

---

### Jobs

#### `POST /jobs`

Create a new verification job.

**Request Body:**
```json
{
  "url": "https://verify.poketwo.net/captcha/1519215866414239746",
  "discord_token": "YOUR_DISCORD_TOKEN",
  "job_type": "poketwo_verify",
  "max_retries": 3,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string (URL) | Yes | Poketwo verification URL |
| `discord_token` | string | Yes | Discord user token (min 10 chars) |
| `job_type` | string | No | Default: `poketwo_verify` |
| `max_retries` | integer | No | 0–10, default from config |
| `metadata` | object | No | Custom metadata |

**Response:** `201 Created` — Job object (token excluded).

#### `GET /jobs`

List jobs.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status |
| `limit` | integer | 1–100, default 50 |
| `offset` | integer | Pagination offset |

**Job Statuses:** `pending`, `queued`, `running`, `waiting_captcha`, `waiting_discord`, `waiting_authorize`, `verifying`, `completed`, `failed`, `retrying`, `cancelled`

#### `GET /jobs/{job_id}`

Get job details, logs, and progress.

#### `POST /jobs/{job_id}/cancel`

Cancel a running or queued job.

#### `GET /jobs/{job_id}/report`

Full execution report with step timeline and screenshots.

#### `GET /jobs/{job_id}/screenshots/{filename}`

Download a job screenshot (PNG).

---

### Admin

#### `POST /admin/cleanup`

Delete completed/failed/cancelled jobs older than configured retention.

---

## WebSocket

### `WS /ws/jobs/{job_id}`

Live job status updates.

**Messages:**
```json
{"type": "snapshot", "job": {...}}
{"type": "update", "job": {...}}
{"type": "ping"}
```

Closes automatically when job reaches terminal state.

### `WS /ws/stats`

Live service statistics (every 2 seconds).

```json
{"type": "stats", "data": {"queue_size": 0, "active_browsers": 1, ...}}
```

---

## Example: Full Workflow

```bash
API="http://localhost:8080/api/v1"
KEY="your-api-key"

# Create job
JOB=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "url": "https://verify.poketwo.net/captcha/1519215866414239746",
    "discord_token": "YOUR_TOKEN"
  }')

JOB_ID=$(echo "$JOB" | node -e "process.stdin.on('data',d=>console.log(JSON.parse(d).id))")
echo "Job ID: $JOB_ID"

# Poll status
while true; do
  STATUS=$(curl -s "$API/jobs/$JOB_ID" -H "X-API-Key: $KEY" \
    | node -e "process.stdin.on('data',d=>console.log(JSON.parse(d).status))")
  echo "Status: $STATUS"
  [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]] && break
  sleep 3
done

# Get report
curl -s "$API/jobs/$JOB_ID/report" -H "X-API-Key: $KEY" | node -e "process.stdin.on('data',d=>console.log(JSON.stringify(JSON.parse(d),null,2)))"
```

## Error Responses

```json
{
  "detail": "Invalid or missing API key"
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request |
| 401 | Invalid API key |
| 404 | Job not found |
| 503 | Service not initialized |
