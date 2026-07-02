"""Application entry point."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from capsolver import __version__
from capsolver.api.routes import router as api_router, set_manager
from capsolver.api.websocket import router as ws_router
from capsolver.core.config import load_config
from capsolver.core.logging import setup_logging, get_logger
from capsolver.core.platform import detect_platform, ensure_display
from capsolver.jobs.manager import JobManager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    setup_logging(
        level=config.logging.level,
        fmt=config.logging.format,
        log_file=config.logging.file,
    )

    platform = detect_platform()
    if not platform.has_display:
        ensure_display(platform, config.platform.display)

    # Ensure data directories exist
    for path in [
        config.resolve_path(config.jobs.artifacts_dir),
        config.resolve_path(config.jobs.store_path).parent,
        config.resolve_path(config.logging.file).parent,
        config.resolve_path(config.browser.user_data_base),
    ]:
        path.mkdir(parents=True, exist_ok=True)

    manager = JobManager()
    await manager.start()
    set_manager(manager)
    app.state.job_manager = manager

    logger.info(
        "cap_solver_started",
        version=__version__,
        platform=platform.os_type.value,
        max_concurrent=config.browser.max_concurrent,
    )

    yield

    await manager.stop()
    logger.info("cap_solver_stopped")


def create_app() -> FastAPI:
    config = load_config()
    app = FastAPI(
        title="Cap-Solver API",
        description="Production-grade browser automation for Discord captcha verification",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    @app.get("/")
    async def root():
        return {
            "name": "Cap-Solver",
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


def cli() -> None:
    parser = argparse.ArgumentParser(description="Cap-Solver browser automation service")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--install-browsers", action="store_true", help="Check browser binary (Brave/Chrome)")
    parser.add_argument("--install-deps", action="store_true", help="Install system dependencies info")
    args = parser.parse_args()

    if args.install_browsers:
        import shutil
        for name in ("brave", "google-chrome-stable", "chromium"):
            path = shutil.which(name)
            if path:
                print(f"Found: {path}")
                return
        print("No browser found. Install Brave or Chrome.")
        return

    if args.install_deps:
        platform = detect_platform()
        from capsolver.core.platform import get_system_dependencies
        deps = get_system_dependencies(platform.os_type)
        print(f"Platform: {platform.os_type.value}")
        print(f"System packages: {', '.join(deps) if deps else 'None required'}")
        return

    if args.config:
        os.environ["CAPSOLVER_CONFIG_PATH"] = args.config

    config = load_config(args.config)
    host = args.host or config.server.host
    port = args.port or config.server.port

    uvicorn.run(
        "capsolver.main:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=config.logging.level.lower(),
    )


if __name__ == "__main__":
    cli()
