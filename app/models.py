from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["transcript"] = "transcript"
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    speaker: str | None = None
    started_at: datetime
    ended_at: datetime
    text: str = Field(min_length=1)
    is_final: bool = True

    @model_validator(mode="after")
    def validate_times(self) -> "TranscriptEvent":
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("日時はtimezone-awareである必要があります")
        if self.ended_at < self.started_at:
            raise ValueError("ended_atはstarted_at以降である必要があります")
        return self


class StatusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["status"] = "status"
    microphone: Literal["initializing", "running", "error"] = "initializing"
    vad: Literal["initializing", "idle", "speech", "error"] = "initializing"
    transcription: Literal["initializing", "idle", "processing", "error"] = (
        "initializing"
    )


@dataclass(slots=True)
class AudioChunk:
    audio: np.ndarray
    captured_at: datetime


@dataclass(slots=True)
class Utterance:
    audio: np.ndarray
    started_at: datetime
    ended_at: datetime
    source: str

