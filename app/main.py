from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, Settings, get_settings
from app.services.pipeline import Pipeline
from app.websocket.manager import ConnectionManager


logger = logging.getLogger(__name__)
STATIC_DIR = PROJECT_ROOT / "static"


async def _broadcast_events(
    pipeline: Pipeline, manager: ConnectionManager
) -> None:
    while True:
        event = await asyncio.to_thread(pipeline.next_broadcast)
        if event is None:
            return
        await manager.broadcast(event.model_dump(mode="json"))


def create_app(
    settings: Settings | None = None,
    pipeline: Pipeline | None = None,
    *,
    enable_pipeline: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    pipeline = pipeline or Pipeline(settings)
    manager = ConnectionManager(
        pipeline.get_status,
        send_timeout_seconds=settings.websocket_send_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        broadcast_task: asyncio.Task[None] | None = None
        if enable_pipeline:
            await asyncio.to_thread(pipeline.start)
            broadcast_task = asyncio.create_task(
                _broadcast_events(pipeline, manager), name="websocket-broadcaster"
            )
        try:
            yield
        finally:
            if enable_pipeline:
                await asyncio.to_thread(pipeline.stop)
                if broadcast_task is not None:
                    try:
                        await asyncio.wait_for(broadcast_task, timeout=6.0)
                    except asyncio.TimeoutError:
                        broadcast_task.cancel()
                        logger.warning("broadcast worker did not stop in time")

    app = FastAPI(
        title="本部 Live Transcript",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.pipeline = pipeline
    app.state.connection_manager = manager
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str | int]:
        status = pipeline.get_status()
        values = status.model_dump(exclude={"type"})
        return {
            "status": "ok" if "error" not in values.values() else "degraded",
            **values,
            "clients": manager.client_count,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        try:
            await manager.connect(websocket)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WebSocket connection failed")
        finally:
            await manager.disconnect(websocket)

    return app


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


_settings = get_settings()
configure_logging(_settings)
app = create_app(_settings)

