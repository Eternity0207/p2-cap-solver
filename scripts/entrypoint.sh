#!/bin/bash
set -euo pipefail

# Start Xvfb virtual display for headless browser automation
export DISPLAY="${DISPLAY:-:99}"

if ! pgrep -f "Xvfb ${DISPLAY}" > /dev/null 2>&1; then
    echo "Starting Xvfb on display ${DISPLAY}..."
    Xvfb "${DISPLAY}" -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
    sleep 1
fi

exec "$@"
