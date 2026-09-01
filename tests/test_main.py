from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class MainAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(Settings(_env_file=None), enable_pipeline=False)

    def test_root_serves_frontend(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("本部 Live Transcript", response.text)

    def test_health_includes_status_and_clients(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "microphone": "initializing",
                "vad": "initializing",
                "transcription": "initializing",
                "clients": 0,
            },
        )

    def test_websocket_receives_initial_status(self) -> None:
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws") as websocket:
                payload = websocket.receive_json()
        self.assertEqual(payload["type"], "status")


if __name__ == "__main__":
    unittest.main()

