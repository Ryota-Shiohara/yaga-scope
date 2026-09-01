from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from app.audio.capture import AudioCapture
from app.audio.vad import StreamingVad, load_streaming_vad
from app.config import Settings
from app.models import AudioChunk, StatusEvent, TranscriptEvent, Utterance
from app.transcription.whisper_worker import WhisperTranscriber


logger = logging.getLogger(__name__)
_STOP = object()
Event = StatusEvent | TranscriptEvent
T = TypeVar("T")


@dataclass(slots=True)
class PipelineDependencies:
    vad_loader: Callable[[Settings], StreamingVad] = load_streaming_vad
    transcriber_loader: Callable[[Settings], WhisperTranscriber] = (
        WhisperTranscriber.load
    )
    capture_factory: Callable[[Settings, queue.Queue[object]], AudioCapture] = (
        AudioCapture
    )


class StatusStore:
    def __init__(self) -> None:
        self._status = StatusEvent()
        self._lock = threading.Lock()

    def get(self) -> StatusEvent:
        with self._lock:
            return self._status.model_copy(deep=True)

    def update(self, **changes: str) -> StatusEvent:
        with self._lock:
            self._status = self._status.model_copy(update=changes)
            return self._status.model_copy(deep=True)


class Pipeline:
    """音声、VAD、Whisper、配信を有界Queueで疎結合にする。"""

    def __init__(
        self,
        settings: Settings,
        dependencies: PipelineDependencies | None = None,
    ) -> None:
        self.settings = settings
        self.dependencies = dependencies or PipelineDependencies()
        self.audio_queue: queue.Queue[object] = queue.Queue(
            maxsize=settings.audio_queue_size
        )
        self.utterance_queue: queue.Queue[object] = queue.Queue(
            maxsize=settings.utterance_queue_size
        )
        self.broadcast_queue: queue.Queue[object] = queue.Queue(
            maxsize=settings.broadcast_queue_size
        )
        self.status = StatusStore()
        self._stop = threading.Event()
        self._vad: StreamingVad | None = None
        self._transcriber: WhisperTranscriber | None = None
        self._capture: AudioCapture | None = None
        self._threads: list[threading.Thread] = []

    def get_status(self) -> StatusEvent:
        return self.status.get()

    def next_broadcast(self, timeout: float | None = None) -> Event | None:
        try:
            item = self.broadcast_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return None if item is _STOP else item  # type: ignore[return-value]

    def start(self) -> None:
        logger.info("application start")
        self._stop.clear()
        self._publish_status()

        try:
            self._vad = self.dependencies.vad_loader(self.settings)
            self._set_status(vad="idle")
        except Exception:
            logger.exception("VAD model loading failed")
            self._set_status(vad="error")

        try:
            self._transcriber = self.dependencies.transcriber_loader(self.settings)
            self._set_status(transcription="idle")
        except Exception:
            logger.exception("Whisper model loading failed")
            self._set_status(transcription="error")

        self._threads = [
            threading.Thread(target=self._vad_loop, name="vad-worker", daemon=True),
            threading.Thread(
                target=self._transcription_loop, name="whisper-worker", daemon=True
            ),
            threading.Thread(
                target=self._monitor_loop, name="pipeline-monitor", daemon=True
            ),
        ]
        for thread in self._threads:
            thread.start()

        try:
            self._capture = self.dependencies.capture_factory(
                self.settings, self.audio_queue
            )
            self._capture.start()
            logger.info("audio device: %s", self._capture.device_description())
            self._set_status(microphone="running")
        except Exception:
            logger.exception("audio device startup failed")
            self._capture = None
            self._set_status(microphone="error")

    def stop(self) -> None:
        if self._capture is not None:
            try:
                self._capture.stop()
            except Exception:
                logger.exception("audio device shutdown failed")
        self._stop.set()
        self._put_control(self.audio_queue, _STOP)
        for thread in self._threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning("worker did not stop in time: %s", thread.name)
        self._set_status(microphone="initializing")
        self._put_control(self.broadcast_queue, _STOP)
        logger.info("application stopped")

    def _vad_loop(self) -> None:
        try:
            while True:
                item = self.audio_queue.get()
                if item is _STOP:
                    break
                if self._vad is None or not isinstance(item, AudioChunk):
                    continue
                was_speech = self._vad.is_speech
                try:
                    utterance = self._vad.process(item)
                    if self._vad.is_speech and not was_speech:
                        logger.info("speech start")
                        self._set_status(vad="speech")
                    if utterance is not None:
                        logger.info(
                            "speech end: duration=%.2fs",
                            utterance.audio.size / self.settings.audio_sample_rate,
                        )
                        self._set_status(vad="idle")
                        self._put_realtime(self.utterance_queue, utterance, "utterance")
                except Exception:
                    logger.exception("VAD processing failed")
                    self._set_status(vad="error")
            if self._vad is not None:
                utterance = self._vad.flush()
                if utterance is not None:
                    self._put_realtime(self.utterance_queue, utterance, "utterance")
        finally:
            self._put_control(self.utterance_queue, _STOP)

    def _transcription_loop(self) -> None:
        while True:
            item = self.utterance_queue.get()
            if item is _STOP:
                break
            if self._transcriber is None or not isinstance(item, Utterance):
                continue
            self._set_status(transcription="processing")
            logger.info("transcription start")
            try:
                event = self._transcriber.transcribe(item)
                if event is not None:
                    self._put_realtime(self.broadcast_queue, event, "broadcast")
                    logger.info("transcription completed")
                else:
                    logger.info("transcription completed: empty result")
                self._set_status(transcription="idle")
            except Exception:
                logger.exception("ASR error")
                self._set_status(transcription="error")

    def _monitor_loop(self) -> None:
        last_dropped = 0
        last_error: str | None = None
        while not self._stop.wait(1.0):
            capture = self._capture
            if capture is None:
                continue
            dropped = capture.dropped_chunks
            if dropped != last_dropped:
                logger.warning(
                    "audio queue overflow: dropped=%d (+%d)",
                    dropped,
                    dropped - last_dropped,
                )
                last_dropped = dropped
            if capture.runtime_error and capture.runtime_error != last_error:
                last_error = capture.runtime_error
                logger.error("audio error: %s", last_error)
                self._set_status(microphone="error")

    def _set_status(self, **changes: str) -> None:
        event = self.status.update(**changes)
        self._put_realtime(self.broadcast_queue, event, "broadcast")

    def _publish_status(self) -> None:
        self._put_realtime(self.broadcast_queue, self.status.get(), "broadcast")

    @staticmethod
    def _put_control(target: queue.Queue[object], item: object) -> None:
        while True:
            try:
                target.put_nowait(item)
                return
            except queue.Full:
                try:
                    target.get_nowait()
                except queue.Empty:
                    pass

    @staticmethod
    def _put_realtime(
        target: queue.Queue[object], item: object, queue_name: str
    ) -> None:
        try:
            target.put_nowait(item)
        except queue.Full:
            try:
                target.get_nowait()
                target.put_nowait(item)
                logger.warning("%s queue overflow: oldest item dropped", queue_name)
            except (queue.Empty, queue.Full):
                logger.warning("%s queue overflow: new item dropped", queue_name)
