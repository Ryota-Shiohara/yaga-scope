from __future__ import annotations

import queue
from datetime import datetime, timedelta, timezone, tzinfo
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from app.config import Settings
from app.models import AudioChunk


def resolve_timezone(name: str) -> tzinfo:
    """Windowsにtzdataがなくても既知のJST設定を利用できるようにする。"""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Tokyo":
            return timezone(timedelta(hours=9), name="JST")
        raise


class AudioCapture:
    """sounddevice callbackからPCMを有界Queueへ渡す。"""

    def __init__(self, settings: Settings, output_queue: queue.Queue[object]) -> None:
        self.settings = settings
        self.output_queue = output_queue
        self._stream: Any | None = None
        self._lock = Lock()
        self._dropped_chunks = 0
        self._runtime_error: str | None = None
        self._timezone = resolve_timezone(settings.timezone)

    @property
    def dropped_chunks(self) -> int:
        with self._lock:
            return self._dropped_chunks

    @property
    def runtime_error(self) -> str | None:
        with self._lock:
            return self._runtime_error

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        # callbackではコピーとQueue投入以外の重い処理を行わない。
        audio = np.asarray(indata[:, 0], dtype=np.float32).copy()
        captured_at = datetime.now(self._timezone) - timedelta(
            seconds=frames / self.settings.audio_sample_rate
        )
        chunk = AudioChunk(audio=audio, captured_at=captured_at)
        if status:
            with self._lock:
                self._runtime_error = str(status)
        try:
            self.output_queue.put_nowait(chunk)
        except queue.Full:
            with self._lock:
                self._dropped_chunks += 1

    def start(self) -> None:
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            dtype="float32",
            blocksize=self.settings.audio_block_size,
            device=self.settings.audio_device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
        finally:
            self._stream.close()
            self._stream = None

    def device_description(self) -> str:
        import sounddevice as sd

        device = sd.query_devices(self.settings.audio_device, "input")
        return str(device.get("name", self.settings.audio_device or "default"))
