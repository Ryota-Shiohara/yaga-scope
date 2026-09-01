from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from app.audio.vad import StreamingVad
from app.config import Settings
from app.models import AudioChunk


class FakeIterator:
    def __init__(self, events: list[dict[str, int] | None]) -> None:
        self.events = iter(events)
        self.reset_count = 0

    def __call__(
        self, chunk: np.ndarray, return_seconds: bool = False
    ) -> dict[str, int] | None:
        return next(self.events, None)

    def reset_states(self) -> None:
        self.reset_count += 1


class StreamingVadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None, vad_speech_pad_ms=64)
        self.started = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)

    def chunk(self, index: int) -> AudioChunk:
        return AudioChunk(
            audio=np.full(512, index, dtype=np.float32),
            captured_at=self.started + timedelta(seconds=index * 512 / 16000),
        )

    def test_builds_utterance_with_pre_roll(self) -> None:
        iterator = FakeIterator(
            [None, {"start": 512}, None, {"end": 1536}]
        )
        vad = StreamingVad(self.settings, iterator, lambda value: value)

        results = [vad.process(self.chunk(index)) for index in range(4)]
        utterance = results[-1]

        self.assertIsNotNone(utterance)
        assert utterance is not None
        self.assertEqual(utterance.source, "hq_mic")
        self.assertEqual(utterance.audio.dtype, np.float32)
        self.assertEqual(utterance.audio.size, 4 * 512)
        self.assertEqual(utterance.started_at, self.started + timedelta(seconds=512 / 16000))
        self.assertEqual(utterance.ended_at, self.started + timedelta(seconds=1536 / 16000))
        self.assertFalse(vad.is_speech)

    def test_flush_returns_active_utterance_and_resets_model(self) -> None:
        iterator = FakeIterator([{"start": 0}, None])
        vad = StreamingVad(self.settings, iterator, lambda value: value)
        vad.process(self.chunk(0))
        vad.process(self.chunk(1))

        utterance = vad.flush()

        self.assertIsNotNone(utterance)
        self.assertEqual(iterator.reset_count, 1)
        self.assertFalse(vad.is_speech)

    def test_idle_flush_only_resets_model(self) -> None:
        iterator = FakeIterator([])
        vad = StreamingVad(self.settings, iterator, lambda value: value)
        self.assertIsNone(vad.flush())
        self.assertEqual(iterator.reset_count, 1)


if __name__ == "__main__":
    unittest.main()

