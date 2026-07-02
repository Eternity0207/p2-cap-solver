#!/usr/bin/env bash
# Cap-Solver one-command deployment script
# Supports: Ubuntu, Debian, Arch Linux, Windows (Git Bash/WSL)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[cap-solver]${NC} $*"; }
warn() { echo -e "${YELLOW}[cap-solver]${NC} $*"; }
error() { echo -e "${RED}[cap-solver]${NC} $*" >&2; }

detect_os() {
    case "$(uname -s)" in
        Linux*)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                echo "$ID"
            else
                echo "linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

install_system_deps() {
    local os="$1"
    log "Installing system dependencies for: $os"

    case "$os" in
        ubuntu|debian|pop)
            sudo apt-get update
            sudo apt-get install -y \
                python3 python3-pip python3-venv \
                xvfb libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
                libgbm1 libasound2 libgtk-3-0 fonts-liberation curl
            ;;
        arch|manjaro)
            sudo pacman -Sy --needed --noconfirm \
                python python-pip \
                xorg-server-xvfb nss atk libdrm libxkbcommon mesa \
                alsa-lib gtk3 ttf-liberation curl
            ;;
        windows)
            warn "On Windows, install Python 3.11+ from python.org"
            ;;
        *)
            warn "Unknown OS. Install Python 3.11+, xvfb, and Playwright deps manually."
            ;;
    esac
}

setup_venv() {
    if [ ! -d ".venv" ]; then
        log "Creating virtual environment..."
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -e .
    playwright install chromium
    playwright install-deps chromium 2>/dev/null || true
}

setup_dirs() {
    mkdir -p data/{logs,artifacts,browser_profiles}
    mkdir -p extensions/nopecha extensions/discord-token-login
    if [ ! -f .env ]; then
        cp .env.example .env
        warn "Created .env from template. Set CAPSOLVER_API_KEY before production use."
    fi
    if [ ! -f config/local.yaml ]; then
        cat > config/local.yaml << 'EOF'
# Local overrides - edit as needed
server:
  api_key: ""  # Or set via CAPSOLVER_API_KEY in .env
EOF
    fi
}

check_extensions() {
    local missing=0
    if [ ! -f "extensions/nopecha/manifest.json" ]; then
        warn "NopeCHA extension not found at extensions/nopecha/"
        missing=1
    fi
    if [ ! -f "extensions/discord-token-login/manifest.json" ]; then
        warn "Discord token login extension not found at extensions/discord-token-login/"
        missing=1
    fi
    if [ "$missing" -eq 1 ]; then
        warn "Run: ./scripts/setup-extensions.sh for installation instructions"
    fi
}

deploy_docker() {
    log "Deploying with Docker..."
    if ! command -v docker &>/dev/null; then
        error "Docker not installed. Install Docker first."
        exit 1
    fi
    setup_dirs
    docker compose build
    docker compose up -d
    log "Cap-Solver running at http://localhost:${PORT:-8080}"
    log "API docs: http://localhost:${PORT:-8080}/docs"
}

deploy_native() {
    local os
    os=$(detect_os)
    install_system_deps "$os"
    setup_venv
    setup_dirs
    check_extensions

    log "Starting Cap-Solver..."
    # shellcheck disable=SC1091
    source .venv/bin/activate

    # Start Xvfb on Linux if no display
    if [ "$os" != "windows" ] && [ -z "${DISPLAY:-}" ]; then
        if command -v Xvfb &>/dev/null; then
            export DISPLAY=:99
            if ! pgrep -f "Xvfb :99" > /dev/null; then
                Xvfb :99 -screen 0 1280x720x24 -ac &
                sleep 1
            fi
        fi
    fi

    # Load .env if present
    if [ -f .env ]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi

    exec cap-solver --host 0.0.0.0 --port "${PORT:-8080}"
}

usage() {
    cat << EOF
Cap-Solver Deployment Script

Usage: $0 [command]

Commands:
  native    Install and run natively (default)
  docker    Build and run with Docker Compose
  setup     Install dependencies only (no start)
  deps      Install system packages only

Examples:
  $0                  # Native deployment
  $0 docker           # Docker deployment
  PORT=9000 $0        # Custom port

EOF
}

main() {
    local cmd="${1:-native}"
    case "$cmd" in
        native) deploy_native ;;
        docker) deploy_docker ;;
        setup)
            os=$(detect_os)
            install_system_deps "$os"
            setup_venv
            setup_dirs
            check_extensions
            log "Setup complete. Run: $0 native"
            ;;
        deps)
            install_system_deps "$(detect_os)"
            ;;
        -h|--help) usage ;;
        *) error "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"
