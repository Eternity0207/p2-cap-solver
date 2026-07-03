FROM node:22-bookworm-slim

LABEL maintainer="Cap-Solver"
LABEL description="Playwright browser automation for Discord captcha verification"

ENV NODE_ENV=production \
    CAPSOLVER_BASE_DIR=/app \
    DISPLAY=:99 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev && npx playwright install chromium --with-deps

COPY src/ src/
COPY config/ config/
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /app/data/logs /app/data/artifacts /app/data/browser_profiles /app/extensions

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["node", "src/index.js"]
