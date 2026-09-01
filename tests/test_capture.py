from __future__ import annotations

import queue
import unittest
from datetime import datetime, timedelta

import numpy as np

from app.audio.capture import AudioCapture, resolve_timezone
from app.config import Settings
from app.models import AudioChunk


class AudioCaptureTest(unittest.TestCase):
    def test_tokyo_timezone_has_nine_hour_offset(self) -> None:
        tokyo = resolve_timezone("Asia/Tokyo")
        moment = datetime(2026, 9, 2, 10, 0, tzinfo=tokyo)
        self.assertEqual(moment.utcoffset(), timedelta(hours=9))

    def test_callback_copies_mono_audio_into_queue(self) -> None:
        output: queue.Queue[object] = queue.Queue(maxsize=2)
        capture = AudioCapture(Settings(_env_file=None), output)
        source = np.ones((512, 1), dtype=np.float32)

        capture._callback(source, 512, None, None)
        source.fill(0)

        item = output.get_nowait()
        self.assertIsInstance(item, AudioChunk)
        assert isinstance(item, AudioChunk)
        self.assertTrue(np.all(item.audio == 1))
        self.assertEqual(item.captured_at.utcoffset(), timedelta(hours=9))

    def test_callback_counts_overflow_without_blocking(self) -> None:
        output: queue.Queue[object] = queue.Queue(maxsize=1)
        capture = AudioCapture(Settings(_env_file=None), output)
        source = np.zeros((512, 1), dtype=np.float32)
        capture._callback(source, 512, None, None)
        capture._callback(source, 512, None, None)
        self.assertEqual(capture.dropped_chunks, 1)


if __name__ == "__main__":
    unittest.main()

