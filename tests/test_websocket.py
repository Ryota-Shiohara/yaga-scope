from __future__ import annotations

import asyncio
import unittest

from app.models import StatusEvent
from app.websocket.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, fail_send: bool = False) -> None:
        self.accepted = False
        self.fail_send = fail_send
        self.messages: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        if self.fail_send:
            raise RuntimeError("client disconnected")
        self.messages.append(payload)


class ConnectionManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_connect_sends_current_status(self) -> None:
        manager = ConnectionManager(
            lambda: StatusEvent(microphone="running", vad="idle", transcription="idle")
        )
        socket = FakeWebSocket()

        await manager.connect(socket)  # type: ignore[arg-type]

        self.assertTrue(socket.accepted)
        self.assertEqual(manager.client_count, 1)
        self.assertEqual(socket.messages[0]["type"], "status")
        self.assertEqual(socket.messages[0]["microphone"], "running")

    async def test_failed_client_does_not_block_other_clients(self) -> None:
        manager = ConnectionManager(StatusEvent)
        healthy = FakeWebSocket()
        failed = FakeWebSocket()
        await manager.connect(healthy)  # type: ignore[arg-type]
        await manager.connect(failed)  # type: ignore[arg-type]
        failed.fail_send = True

        await manager.broadcast({"type": "transcript", "text": "了解しました"})

        self.assertEqual(healthy.messages[-1]["text"], "了解しました")
        self.assertEqual(manager.client_count, 1)

    async def test_slow_client_times_out(self) -> None:
        class SlowWebSocket(FakeWebSocket):
            async def send_json(self, payload: dict[str, object]) -> None:
                await asyncio.sleep(0.05)

        manager = ConnectionManager(StatusEvent, send_timeout_seconds=0.01)
        socket = SlowWebSocket()
        with self.assertRaises(asyncio.TimeoutError):
            await manager.connect(socket)  # type: ignore[arg-type]
        self.assertEqual(manager.client_count, 0)


if __name__ == "__main__":
    unittest.main()

