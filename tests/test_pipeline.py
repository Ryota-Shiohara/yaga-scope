from __future__ import annotations

import queue
import time
import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from app.config import Settings
from app.models import AudioChunk, TranscriptEvent, Utterance
from app.services.pipeline import Pipeline, PipelineDependencies


class FakeVad:
    is_speech = False

    def __init__(self) -> None:
        self.index = 0

    def process(self, chunk: AudioChunk) -> Utterance:
        self.index += 1
        return Utterance(
            audio=chunk.audio,
            started_at=chunk.captured_at,
            ended_at=chunk.captured_at + timedelta(milliseconds=32),
            source="hq_mic",
        )

    def flush(self) -> None:
        return None


class FakeTranscriber:
    def __init__(self) -> None:
        self.index = 0

    def transcribe(self, utterance: Utterance) -> TranscriptEvent:
        self.index += 1
        return TranscriptEvent(
            source=utterance.source,
            started_at=utterance.started_at,
            ended_at=utterance.ended_at,
            text=f"発話{self.index}",
        )


class FakeCapture:
    dropped_chunks = 0
    runtime_error = None

    def __init__(self, settings: Settings, output: queue.Queue[object]) -> None:
        self.settings = settings
        self.output = output

    def start(self) -> None:
        now = datetime.now(timezone.utc)
        for index in range(3):
            self.output.put_nowait(
                AudioChunk(
                    audio=np.zeros(512, dtype=np.float32),
                    captured_at=now + timedelta(milliseconds=32 * index),
                )
            )

    def stop(self) -> None:
        return None

    def device_description(self) -> str:
        return "fake microphone"


class PipelineTest(unittest.TestCase):
    def test_workers_keep_order_across_queues(self) -> None:
        settings = Settings(_env_file=None)
        dependencies = PipelineDependencies(
            vad_loader=lambda _settings: FakeVad(),  # type: ignore[arg-type]
            transcriber_loader=lambda _settings: FakeTranscriber(),  # type: ignore[arg-type]
            capture_factory=FakeCapture,  # type: ignore[arg-type]
        )
        pipeline = Pipeline(settings, dependencies)
        transcripts: list[TranscriptEvent] = []

        pipeline.start()
        deadline = time.monotonic() + 2
        try:
            while len(transcripts) < 3 and time.monotonic() < deadline:
                event = pipeline.next_broadcast(timeout=0.1)
                if isinstance(event, TranscriptEvent):
                    transcripts.append(event)
        finally:
            pipeline.stop()

        self.assertEqual([event.text for event in transcripts], ["発話1", "発話2", "発話3"])
        self.assertEqual(pipeline.get_status().microphone, "initializing")


if __name__ == "__main__":
    unittest.main()

