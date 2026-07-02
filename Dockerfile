FROM python:3.12-slim-bookworm

LABEL maintainer="Cap-Solver"
LABEL description="Browser automation for Discord captcha verification"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CAPSOLVER_BASE_DIR=/app \
    DISPLAY=:99 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System dependencies for Playwright + Xvfb on Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libgtk-3-0 \
    fonts-liberation \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir -e . && \
    patchright install chromium

# Create data directories
RUN mkdir -p /app/data/logs /app/data/artifacts /app/data/browser_profiles /app/extensions

COPY extensions/README.md extensions/
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["cap-solver"]
