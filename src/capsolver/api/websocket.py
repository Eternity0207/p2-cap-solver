"""WebSocket live job status updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from capsolver.api.routes import get_manager
from capsolver.jobs.models import Job

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    manager = get_manager()

    job = await manager.get_job(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return

    await websocket.send_json({"type": "snapshot", "job": job.to_public_dict()})

    if job.status.value in ("completed", "failed", "cancelled"):
        await websocket.close()
        return

    update_event = asyncio.Event()
    latest_job: dict[str, Any] = {"job": job}

    async def on_update(updated: Job) -> None:
        if updated.id == job_id:
            latest_job["job"] = updated
            update_event.set()

    manager.subscribe(job_id, on_update)

    try:
        while True:
            try:
                await asyncio.wait_for(update_event.wait(), timeout=30.0)
                update_event.clear()
                current: Job = latest_job["job"]
                await websocket.send_json({"type": "update", "job": current.to_public_dict()})
                if current.status.value in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(job_id, on_update)


@router.websocket("/ws/stats")
async def stats_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    manager = get_manager()

    try:
        while True:
            stats = await manager.get_stats()
            await websocket.send_json({"type": "stats", "data": stats})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
