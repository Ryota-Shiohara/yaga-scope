from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from app.config import Settings
from app.models import Utterance
from app.transcription.whisper_worker import WhisperTranscriber


class FakeWhisperModel:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio: np.ndarray, **options: object):
        self.calls.append(options)
        return (SimpleNamespace(text=text) for text in self.texts), object()


class WhisperTranscriberTest(unittest.TestCase):
    def utterance(self) -> Utterance:
        now = datetime.now(timezone.utc)
        return Utterance(
            audio=np.zeros(16000, dtype=np.float32),
            started_at=now,
            ended_at=now + timedelta(seconds=1),
            source="hq_mic",
        )

    def test_evaluates_segments_and_joins_text(self) -> None:
        model = FakeWhisperModel([" ステージ担当者", "お願いします "])
        transcriber = WhisperTranscriber(Settings(_env_file=None), model)

        event = transcriber.transcribe(self.utterance())

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.text, "ステージ担当者お願いします")
        self.assertEqual(model.calls[0]["language"], "ja")
        self.assertEqual(model.calls[0]["beam_size"], 1)
        self.assertFalse(model.calls[0]["vad_filter"])
        self.assertIsNone(model.calls[0]["hotwords"])

    def test_passes_configured_hotwords_to_model(self) -> None:
        model = FakeWhisperModel([" 矢上祭本部です "])
        transcriber = WhisperTranscriber(
            Settings(
                _env_file=None,
                whisper_hotwords="矢上祭、本部、実行委員、ステージ",
            ),
            model,
        )

        event = transcriber.transcribe(self.utterance())

        self.assertIsNotNone(event)
        self.assertEqual(
            model.calls[0]["hotwords"],
            "矢上祭、本部、実行委員、ステージ",
        )

    def test_blank_hotwords_are_disabled(self) -> None:
        settings = Settings(_env_file=None, whisper_hotwords="   ")
        self.assertIsNone(settings.whisper_hotwords)

    def test_replaces_hiragana_and_katakana_names(self) -> None:
        model = FakeWhisperModel([" なるあきさんとリョウタさん "])
        transcriber = WhisperTranscriber(
            Settings(
                _env_file=None,
                transcript_replacements={
                    "なるあき": "成晃",
                    "リョウタ": "遼大",
                },
            ),
            model,
        )

        event = transcriber.transcribe(self.utterance())

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.text, "成晃さんと遼大さん")

    def test_replaces_longer_alias_before_shorter_alias(self) -> None:
        model = FakeWhisperModel([" やがみさい本部 "])
        transcriber = WhisperTranscriber(
            Settings(
                _env_file=None,
                transcript_replacements={
                    "やがみ": "矢上",
                    "やがみさい": "矢上祭",
                },
            ),
            model,
        )

        event = transcriber.transcribe(self.utterance())

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.text, "矢上祭本部")

    def test_does_not_emit_empty_text(self) -> None:
        model = FakeWhisperModel(["  "])
        transcriber = WhisperTranscriber(Settings(_env_file=None), model)
        self.assertIsNone(transcriber.transcribe(self.utterance()))


if __name__ == "__main__":
    unittest.main()
