from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

import numpy as np

from app.config import Settings
from app.models import AudioChunk, Utterance


class VadIteratorProtocol(Protocol):
    def __call__(self, chunk: Any, return_seconds: bool = False) -> dict[str, int] | None: ...

    def reset_states(self) -> None: ...


class StreamingVad:
    """VADIteratorのイベントから発話波形を組み立てる。"""

    def __init__(
        self,
        settings: Settings,
        iterator: VadIteratorProtocol,
        tensor_factory: Callable[[np.ndarray], Any],
    ) -> None:
        self.settings = settings
        self.iterator = iterator
        self.tensor_factory = tensor_factory
        pre_roll_chunks = max(
            1,
            int(
                np.ceil(
                    settings.vad_speech_pad_ms
                    * settings.audio_sample_rate
                    / 1000
                    / settings.audio_block_size
                )
            ),
        )
        self._pre_roll: deque[AudioChunk] = deque(maxlen=pre_roll_chunks)
        self._speech_chunks: list[np.ndarray] = []
        self._speech_samples = 0
        self._started_at: datetime | None = None
        self._stream_started_at: datetime | None = None
        self._active = False

    @property
    def is_speech(self) -> bool:
        return self._active

    def process(self, chunk: AudioChunk) -> Utterance | None:
        if self._stream_started_at is None:
            self._stream_started_at = chunk.captured_at

        audio = np.asarray(chunk.audio, dtype=np.float32).reshape(-1)
        event = self.iterator(self.tensor_factory(audio), return_seconds=False)

        if not self._active:
            self._pre_roll.append(AudioChunk(audio=audio, captured_at=chunk.captured_at))
            if event and "start" in event:
                self._active = True
                self._speech_chunks = [item.audio for item in self._pre_roll]
                self._speech_samples = sum(item.size for item in self._speech_chunks)
                self._started_at = self._event_time(event["start"], self._pre_roll[0].captured_at)
                self._pre_roll.clear()
            return None

        self._speech_chunks.append(audio)
        self._speech_samples += audio.size

        if event and "end" in event:
            ended_at = self._event_time(
                event["end"],
                chunk.captured_at
                + timedelta(seconds=audio.size / self.settings.audio_sample_rate),
            )
            utterance = self._finish(ended_at)
            self._pre_roll.append(AudioChunk(audio=audio, captured_at=chunk.captured_at))
            return utterance

        if self._speech_samples >= int(
            self.settings.vad_max_speech_seconds * self.settings.audio_sample_rate
        ):
            ended_at = chunk.captured_at + timedelta(
                seconds=audio.size / self.settings.audio_sample_rate
            )
            utterance = self._finish(ended_at)
            self.iterator.reset_states()
            return utterance

        return None

    def flush(self) -> Utterance | None:
        if not self._active or not self._speech_chunks:
            self.iterator.reset_states()
            return None
        duration = self._speech_samples / self.settings.audio_sample_rate
        ended_at = (self._started_at or datetime.now().astimezone()) + timedelta(
            seconds=duration
        )
        utterance = self._finish(ended_at)
        self.iterator.reset_states()
        return utterance

    def _event_time(self, sample: int, fallback: datetime) -> datetime:
        if self._stream_started_at is None:
            return fallback
        return self._stream_started_at + timedelta(
            seconds=sample / self.settings.audio_sample_rate
        )

    def _finish(self, ended_at: datetime) -> Utterance:
        started_at = self._started_at or ended_at
        if ended_at < started_at:
            ended_at = started_at
        utterance = Utterance(
            audio=np.concatenate(self._speech_chunks).astype(np.float32, copy=False),
            started_at=started_at,
            ended_at=ended_at,
            source=self.settings.source_id,
        )
        self._speech_chunks = []
        self._speech_samples = 0
        self._started_at = None
        self._active = False
        return utterance


def load_streaming_vad(settings: Settings) -> StreamingVad:
    import torch
    from silero_vad import VADIterator, load_silero_vad

    torch.set_num_threads(1)
    model = load_silero_vad()
    iterator = VADIterator(
        model,
        threshold=settings.vad_threshold,
        sampling_rate=settings.audio_sample_rate,
        min_silence_duration_ms=settings.vad_min_silence_ms,
        speech_pad_ms=settings.vad_speech_pad_ms,
    )
    return StreamingVad(settings, iterator, torch.from_numpy)

