from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.models import TranscriptEvent, Utterance


logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """起動時に一度だけロードしたfaster-whisperモデルを再利用する。"""

    def __init__(self, settings: Settings, model: Any) -> None:
        self.settings = settings
        self.model = model

    @classmethod
    def load(cls, settings: Settings) -> "WhisperTranscriber":
        from faster_whisper import WhisperModel

        logger.info("Whisper loading: model=%s", settings.whisper_model)
        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper loaded")
        return cls(settings, model)

    def transcribe(self, utterance: Utterance) -> TranscriptEvent | None:
        segments, _info = self.model.transcribe(
            utterance.audio,
            language=self.settings.whisper_language,
            beam_size=self.settings.whisper_beam_size,
            vad_filter=False,
            hotwords=self.settings.whisper_hotwords,
        )
        text = "".join(segment.text for segment in segments).strip()
        text = self._apply_replacements(text)
        if not text:
            return None
        return TranscriptEvent(
            source=utterance.source,
            started_at=utterance.started_at,
            ended_at=utterance.ended_at,
            text=text,
        )

    def _apply_replacements(self, text: str) -> str:
        # 部分一致する別名がある場合に備え、長い表記から先に置換する。
        replacements = sorted(
            self.settings.transcript_replacements.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for source, destination in replacements:
            text = text.replace(source, destination)
        return text
