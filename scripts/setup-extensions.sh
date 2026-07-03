#!/usr/bin/env bash
# Helper script to set up browser extensions for Cap-Solver
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXT_DIR="$PROJECT_DIR/extensions"

echo "=== Cap-Solver Extension Setup ==="
echo ""
echo "Cap-Solver requires two Chrome extensions (Manifest V3):"
echo ""
echo "1. NopeCHA - Automatic captcha solver (Turnstile, reCAPTCHA, etc.)"
echo "   Website: https://nopecha.com"
echo "   Chrome Web Store: https://chromewebstore.google.com/detail/nopecha-captcha-solver/dknlfmjaanfblgfdfebhijalfmhmjjjo"
echo ""
echo "2. Discord Token Login - Login to Discord with a token"
echo "   Search Chrome Web Store for 'Discord Token Login' or similar MV3 extension"
echo ""

mkdir -p "$EXT_DIR/nopecha" "$EXT_DIR/discord-token-login"

cat << 'INSTRUCTIONS'

## Manual Installation Steps

### Option A: Download from Chrome Web Store (Recommended)

1. Install the extensions in Chrome/Chromium normally
2. Find the extension folder on your system:

   **Linux:**
   ~/.config/chromium/Default/Extensions/<extension-id>/<version>/
   OR ~/.config/google-chrome/Default/Extensions/<extension-id>/<version>/

   **Windows:**
   %LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions\<extension-id>\<version>\

3. Copy the unpacked extension folder contents to:
   - extensions/nopecha/
   - extensions/discord-token-login/

4. Verify manifest.json exists in each folder:
   ls extensions/nopecha/manifest.json
   ls extensions/discord-token-login/manifest.json

### Option B: Use crx-extract (if you have .crx files)

   pip install crx3
   # Extract and copy to extensions/ directories

### Option C: Clone unpacked builds

   If the extension provides an unpacked GitHub release, clone/download
   directly into the extensions/ directories.

## Verify Installation

   ./scripts/setup-extensions.sh

INSTRUCTIONS

# Check current status
echo ""
echo "=== Current Status ==="
for ext in nopecha discord-token-login; do
    if [ -f "$EXT_DIR/$ext/manifest.json" ]; then
        name=$(node -e "console.log(JSON.parse(require('fs').readFileSync('$EXT_DIR/$ext/manifest.json','utf8')).name||'unknown')" 2>/dev/null || echo "unknown")
        echo "✓ $ext: $name"
    else
        echo "✗ $ext: NOT INSTALLED"
    fi
done
