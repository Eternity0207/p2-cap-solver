#!/usr/bin/env bash
# Clean runtime data — keeps config/extensions, wipes browser state and artifacts
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data"

echo "Stopping processes first..."
"$ROOT/scripts/kill-stale.sh" 2>/dev/null || true

echo "Cleaning data folder..."
for dir in browser_profiles artifacts diagnostics; do
    if [ -d "$DATA/$dir" ]; then
        rm -rf "$DATA/$dir"
        echo "  removed $DATA/$dir"
    fi
    mkdir -p "$DATA/$dir"
done

# Reset job DB (fresh test runs)
if [ -f "$DATA/jobs.db" ]; then
    rm -f "$DATA/jobs.db"
    echo "  removed jobs.db"
fi

# Truncate log (optional — keep file, clear content)
if [ -f "$DATA/logs/cap-solver.log" ]; then
    : > "$DATA/logs/cap-solver.log"
    echo "  cleared cap-solver.log"
fi

mkdir -p "$DATA/logs"
echo "Done. Data folder is clean."
du -sh "$DATA"/* 2>/dev/null || true
