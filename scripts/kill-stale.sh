#!/usr/bin/env bash
# Kill all Cap-Solver and automation browser processes
set -euo pipefail

echo "Stopping Cap-Solver..."
pkill -f "cap-solver" 2>/dev/null || true
pkill -f "uvicorn.*capsolver" 2>/dev/null || true

echo "Stopping automation browsers..."
pkill -f "remote-debugging-port" 2>/dev/null || true
pkill -f "browser_profiles" 2>/dev/null || true
pkill -f "Cap-Solver.*user-data-dir" 2>/dev/null || true

sleep 2

# Clean stale Chromium profile locks (cause crashes on restart)
PROFILES_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/browser_profiles"
if [ -d "$PROFILES_DIR" ]; then
    find "$PROFILES_DIR" -name "SingletonLock" -delete 2>/dev/null || true
    find "$PROFILES_DIR" -name "SingletonSocket" -delete 2>/dev/null || true
    find "$PROFILES_DIR" -name "LOCK" -delete 2>/dev/null || true
    find "$PROFILES_DIR" -name "lockfile" -delete 2>/dev/null || true
    echo "Cleaned profile locks in $PROFILES_DIR"
fi

echo "Done. Remaining:"
pgrep -af "cap-solver|remote-debugging|browser_profiles" || echo "  (none)"
