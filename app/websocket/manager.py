from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from fastapi import WebSocket

from app.models import StatusEvent


logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(
        self,
        status_provider: Callable[[], StatusEvent],
        send_timeout_seconds: float = 2.0,
    ) -> None:
        self.active_connections: set[WebSocket] = set()
        self._status_provider = status_provider
        self._send_timeout_seconds = send_timeout_seconds
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        try:
            await self._send_json(
                websocket, self._status_provider().model_dump(mode="json")
            )
        except Exception:
            await self.disconnect(websocket)
            raise
        logger.info("WebSocket connect: clients=%d", self.client_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info("WebSocket disconnect: clients=%d", self.client_count)

    async def broadcast(self, payload: dict[str, object]) -> None:
        async with self._lock:
            connections = tuple(self.active_connections)
        if not connections:
            return
        results = await asyncio.gather(
            *(self._send_json(connection, payload) for connection in connections),
            return_exceptions=True,
        )
        failed = [
            connection
            for connection, result in zip(connections, results, strict=True)
            if isinstance(result, BaseException)
        ]
        if failed:
            async with self._lock:
                for connection in failed:
                    self.active_connections.discard(connection)
            logger.warning("WebSocket send failed: removed=%d", len(failed))

    async def _send_json(
        self, websocket: WebSocket, payload: dict[str, object]
    ) -> None:
        await asyncio.wait_for(
            websocket.send_json(payload), timeout=self._send_timeout_seconds
        )

