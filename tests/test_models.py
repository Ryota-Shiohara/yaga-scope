from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from app.models import StatusEvent, TranscriptEvent
from app.config import Settings


class TranscriptEventTest(unittest.TestCase):
    def test_serializes_expected_event(self) -> None:
        started = datetime(2026, 9, 2, 10, 32, 14, tzinfo=timezone(timedelta(hours=9)))
        event = TranscriptEvent(
            source="hq_mic",
            started_at=started,
            ended_at=started + timedelta(seconds=2),
            text="ステージ担当者お願いします",
        )

        payload = event.model_dump(mode="json")

        self.assertEqual(payload["type"], "transcript")
        self.assertEqual(payload["source"], "hq_mic")
        self.assertEqual(payload["speaker"], None)
        self.assertTrue(payload["is_final"])
        self.assertIn("+09:00", payload["started_at"])
        self.assertTrue(event.id)

    def test_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValidationError):
            TranscriptEvent(
                source="hq_mic",
                started_at=datetime(2026, 9, 2, 10, 0),
                ended_at=datetime(2026, 9, 2, 10, 1),
                text="テスト",
            )

    def test_rejects_reversed_time_range(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            TranscriptEvent(
                source="hq_mic",
                started_at=now,
                ended_at=now - timedelta(seconds=1),
                text="テスト",
            )


class StatusEventTest(unittest.TestCase):
    def test_initial_status(self) -> None:
        status = StatusEvent()
        self.assertEqual(status.type, "status")
        self.assertEqual(status.microphone, "initializing")
        self.assertEqual(status.vad, "initializing")
        self.assertEqual(status.transcription, "initializing")


class SettingsTest(unittest.TestCase):
    def test_fixed_audio_values_accept_environment_strings(self) -> None:
        settings = Settings(
            _env_file=None,
            audio_sample_rate="16000",
            audio_channels="1",
            audio_block_size="512",
        )
        self.assertEqual(settings.audio_sample_rate, 16000)
        self.assertEqual(settings.audio_channels, 1)
        self.assertEqual(settings.audio_block_size, 512)

    def test_numeric_audio_device_string_becomes_device_index(self) -> None:
        settings = Settings(_env_file=None, audio_device="1")
        self.assertEqual(settings.audio_device, 1)
        self.assertIsInstance(settings.audio_device, int)

    def test_named_audio_device_remains_string(self) -> None:
        settings = Settings(_env_file=None, audio_device="マイク配列")
        self.assertEqual(settings.audio_device, "マイク配列")


if __name__ == "__main__":
    unittest.main()
