from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """環境変数から読み込むアプリケーション設定。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_block_size: int = 512
    audio_device: int | str | None = None

    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_min_silence_ms: int = Field(default=600, ge=100, le=5000)
    vad_speech_pad_ms: int = Field(default=250, ge=0, le=2000)
    vad_max_speech_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

    whisper_model: Literal["tiny", "base", "small", "medium"] = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "ja"
    whisper_beam_size: int = Field(default=1, ge=1, le=10)
    whisper_hotwords: str | None = Field(default=None, max_length=2000)
    transcript_replacements: dict[str, str] = Field(default_factory=dict)

    source_id: str = Field(default="hq_mic", min_length=1, max_length=64)
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    timezone: str = "Asia/Tokyo"

    audio_queue_size: int = Field(default=256, ge=8, le=4096)
    utterance_queue_size: int = Field(default=64, ge=2, le=1024)
    broadcast_queue_size: int = Field(default=256, ge=8, le=4096)
    websocket_send_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)
    log_level: str = "INFO"

    @field_validator("source_id", "whisper_language", "whisper_device", "whisper_compute_type")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("空文字は指定できません")
        return value.strip()

    @field_validator("whisper_hotwords", mode="before")
    @classmethod
    def normalize_hotwords(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("transcript_replacements")
    @classmethod
    def validate_replacements(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for source, destination in value.items():
            source = source.strip()
            destination = destination.strip()
            if not source or not destination:
                raise ValueError("置換元と置換先に空文字は指定できません")
            normalized[source] = destination
        return normalized

    @field_validator("audio_device", mode="before")
    @classmethod
    def parse_audio_device(cls, value: object) -> object:
        """.envの数値文字列をsounddeviceのデバイス番号として扱う。"""
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            if normalized.isdecimal():
                return int(normalized)
            return normalized
        return value

    @field_validator("audio_sample_rate")
    @classmethod
    def validate_sample_rate(cls, value: int) -> int:
        if value != 16000:
            raise ValueError("Silero VAD用に16000を指定してください")
        return value

    @field_validator("audio_channels")
    @classmethod
    def validate_channels(cls, value: int) -> int:
        if value != 1:
            raise ValueError("音声入力はmono（1）を指定してください")
        return value

    @field_validator("audio_block_size")
    @classmethod
    def validate_block_size(cls, value: int) -> int:
        if value != 512:
            raise ValueError("16 kHz Silero VAD用に512を指定してください")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
