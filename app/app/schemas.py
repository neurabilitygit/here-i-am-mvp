from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RecordingSessionStart(BaseModel):
    title_hint: str | None = None


class RecordingSessionResponse(BaseModel):
    session_id: str
    upload_url: str


class UploadResponse(BaseModel):
    session_id: str
    flac_path: str


class QueueResponse(BaseModel):
    total_identified: int
    newly_queued: int
    mode: Literal['transcribe', 'analyze']


class JobStatus(BaseModel):
    mode: str
    state: str
    current_file: str | None = None
    detail: str | None = None
    processed: int = 0
    total: int = 0
    completed: bool = False


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = 6


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: int


class MetadataEnvelope(BaseModel):
    session_id: str
    title: str
    summary: str
    topics: list[str]
    people: list[str]
    places: list[str]
    life_period: str | None = None
    emotional_tone: list[str] = Field(default_factory=list)
    source_audio: str
    transcript_path: str
    analysis_model: str
    embedding_model: str
    transcript_word_count: int
    chunk_count: int
    extra: dict[str, Any] = Field(default_factory=dict)
