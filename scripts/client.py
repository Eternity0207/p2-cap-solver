#!/usr/bin/env python3
"""CLI client for Cap-Solver API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def request(method: str, url: str, api_key: str, data: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def cmd_submit(args: argparse.Namespace) -> None:
    result = request(
        "POST",
        f"{args.api_url}/jobs",
        args.api_key,
        {
            "url": args.url,
            "discord_token": args.token,
            "max_retries": args.retries,
        },
    )
    job_id = result["id"]
    print(f"Job created: {job_id}")
    print(f"Status: {result['status']}")

    if not args.wait:
        print(json.dumps(result, indent=2))
        return

    while True:
        time.sleep(args.interval)
        job = request("GET", f"{args.api_url}/jobs/{job_id}", args.api_key)
        status = job["status"]
        progress = job.get("progress", {})
        print(f"[{status}] {progress.get('current_step', '')} - {progress.get('message', '')}")
        if status in ("completed", "failed", "cancelled"):
            report = request("GET", f"{args.api_url}/jobs/{job_id}/report", args.api_key)
            print(json.dumps(report["report"]["summary"], indent=2))
            sys.exit(0 if status == "completed" else 1)


def cmd_status(args: argparse.Namespace) -> None:
    job = request("GET", f"{args.api_url}/jobs/{args.job_id}", args.api_key)
    print(json.dumps(job, indent=2, default=str))


def cmd_health(args: argparse.Namespace) -> None:
    result = request("GET", f"{args.api_url.replace('/api/v1', '')}/api/v1/health", "")
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cap-Solver CLI client")
    parser.add_argument("--api-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--api-key", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser("submit", help="Submit a verification job")
    submit.add_argument("url", help="Poketwo verification URL")
    submit.add_argument("token", help="Discord token")
    submit.add_argument("--retries", type=int, default=3)
    submit.add_argument("--wait", action="store_true", help="Wait for completion")
    submit.add_argument("--interval", type=float, default=3.0)
    submit.set_defaults(func=cmd_submit)

    status = sub.add_parser("status", help="Get job status")
    status.add_argument("job_id")
    status.set_defaults(func=cmd_status)

    health = sub.add_parser("health", help="Health check")
    health.set_defaults(func=cmd_health)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
