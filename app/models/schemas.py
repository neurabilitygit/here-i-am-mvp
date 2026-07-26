from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecordingUploadResponse(BaseModel):
    session_id: str
    message: str
    recording_mode: Literal['solo', 'conversation'] = 'solo'


class JobProgress(BaseModel):
    id: str
    mode: str
    status: str
    message: str
    current_file: Optional[str] = None
    processed: int = 0
    total: int = 0
    completed: bool = False
    error: Optional[str] = None
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


class BenchmarkAnswer(BaseModel):
    provider: Literal['local', 'openai']
    model: str
    answer: str
    elapsed_seconds: float


class ChatBenchmarkResponse(BaseModel):
    question: str
    mode: Literal['PERSONAL', 'GENERAL', 'HYBRID']
    sources: list['ChatSource'] = Field(default_factory=list)
    retrieval_seconds: float
    results: list[BenchmarkAnswer]


class ChatResponse(BaseModel):
    answer: str
    mode: Literal['PERSONAL', 'GENERAL', 'HYBRID'] = 'GENERAL'
    sources: list['ChatSource'] = Field(default_factory=list)
    elapsed_seconds: float | None = None


class GenericStatus(BaseModel):
    status: str
    detail: str


class PromptOfTheDay(BaseModel):
    prompt: str


class QuizPrompt(BaseModel):
    session_id: str
    topic_hint: str
    quote: str


class SealRequest(BaseModel):
    unlock_at: datetime


class AuthLoginRequest(BaseModel):
    passphrase: str = Field(min_length=1, max_length=512)


class AuthStatus(BaseModel):
    authenticated: bool
    required: bool


class ClientActivityEvent(BaseModel):
    event: str = Field(min_length=1, max_length=80, pattern=r'^[a-z][a-z0-9_]*$')
    page_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    sequence: int = Field(ge=1, le=1_000_000_000)
    scene: str = Field(default='', max_length=40, pattern=r'^[a-z0-9_-]*$')
    occurred_at: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)


class ChatSource(BaseModel):
    session_id: str
    title: str = ''
    topics: str = ''
    distance: float | None = None


class StyleProfile(BaseModel):
    sentence_rhythm: list[str] | str = Field(default_factory=list)
    vocabulary_style: list[str] | str = Field(default_factory=list)
    rhetorical_habits: list[str] | str = Field(default_factory=list)
    emotional_register: list[str] | str = Field(default_factory=list)
    pacing_style: list[str] | str = Field(default_factory=list)
    humor_style: list[str] | str = Field(default_factory=list)
    certainty_style: list[str] | str = Field(default_factory=list)
    storytelling_style: list[str] | str = Field(default_factory=list)
    values_signals: list[str] | str = Field(default_factory=list)
    recurring_concerns: list[str] | str = Field(default_factory=list)
    conversational_stance: list[str] | str = Field(default_factory=list)
    prosody_notes: list[str] | str = Field(default_factory=list)


class TranscriptMetadata(BaseModel):
    session_id: str
    title: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    time_period: str | list[str] = ''
    emotional_tone: str | list[str] = Field(default_factory=list)
    content_type: str = 'autobiography'
    notable_events: list[str] = Field(default_factory=list)
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    style_exemplars: dict[str, str] = Field(default_factory=dict)
    metadata_version: str = '2.0'
    audio_path: str = ''
    transcript_path: str = ''


class SessionSummary(BaseModel):
    session_id: str
    title: str
    recorded: bool
    transcribed: bool
    analyzed: bool
    embedded: bool
    archived: bool = False
    audio_bytes: int = 0
    transcript_bytes: int = 0
    updated_at: datetime | None = None
    recording_mode: Literal['solo', 'conversation'] = 'solo'
    speaker_review_status: str = 'not_required'
    speaker_count: int = 1
    recorded_at: str = ''
    time_period: str | list[str] = ''
    emotional_tone: str | list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    notable_events: list[str] = Field(default_factory=list)
    sealed: bool = False
    unlock_at: str | None = None


class SessionDetail(SessionSummary):
    state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    transcript: str | None = None


class TranscriptUpdate(BaseModel):
    transcript: str = Field(min_length=1)
    reason: str = Field(default='manual correction', max_length=500)


class SpeakerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    default_role: Literal['memory_subject', 'interviewer', 'other'] = 'other'


class SpeakerProfile(BaseModel):
    speaker_id: str
    display_name: str
    default_role: Literal['memory_subject', 'interviewer', 'other'] = 'other'
    avatar_url: str | None = None
    voice_reference_ready: bool = False
    source_photo_ready: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SpeakerAssignment(BaseModel):
    cluster_id: str = Field(min_length=1, max_length=100)
    speaker_id: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=80)
    role: Literal['memory_subject', 'interviewer', 'other']


class SpeakerAssignmentsUpdate(BaseModel):
    assignments: list[SpeakerAssignment] = Field(min_length=1, max_length=8)


class AvatarGenerationRequest(BaseModel):
    confirm_image_rights: bool


class AvatarJobResponse(BaseModel):
    job_id: str
    status: str
    detail: str


class ReconciliationIssue(BaseModel):
    session_id: str
    code: str
    detail: str


class ReconciliationReport(BaseModel):
    checked_sessions: int
    issue_count: int
    issues: list[ReconciliationIssue] = Field(default_factory=list)
    repair_applied: bool = False


class AvatarPreferences(BaseModel):
    name: str = 'Here I Am'
    skin: str = 'warm'
    hair: str = 'silver'
    hair_style: str = 'soft'
    clothing: str = 'indigo'
    glasses: bool = False
    backdrop: str = 'dusk'


class ExperiencePreferences(BaseModel):
    text_scale: Literal['standard', 'large', 'largest'] = 'large'
    reduce_motion: bool = False
    high_contrast: bool = False
    auto_speak: bool = False
    pre_render_voice: bool = False
    captions: bool = True
    provider: Literal['local', 'openai'] = 'local'
    cloud_model: str = 'gpt-5.4-mini'
    fidelity: Literal['grounded', 'balanced', 'expressive'] = 'balanced'
    avatar: AvatarPreferences = Field(default_factory=AvatarPreferences)
    onboarding_complete: bool = False

    @field_validator('cloud_model')
    @classmethod
    def validate_cloud_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 80 or not all(character.isalnum() or character in '.-_:/' for character in value):
            raise ValueError('Invalid cloud model name')
        return value


class PreferencesUpdate(BaseModel):
    preferences: ExperiencePreferences
    cloud_api_key: str | None = Field(default=None, max_length=500)


class ProviderStatus(BaseModel):
    active: str
    local_ready: bool
    local_model: str
    local_model_available: bool
    cloud_configured: bool
    cloud_key_source: Literal['none', 'environment', 'session'] = 'none'
    cloud_model: str
    cloud_model_allowed: bool
    active_ready: bool
    no_automatic_fallback: bool = True
    embedding_provider: Literal['local_ollama'] = 'local_ollama'
    embedding_model: str


class SpeakerFingerprint(BaseModel):
    version: str = '1.0'
    transcript_count: int = 0
    audio_hours: float = 0
    word_count: int = 0
    average_sentence_words: float = 0
    sentence_length_variation: float = 0
    average_words_per_minute: float | None = None
    contraction_rate: float = 0
    question_rate: float = 0
    exclamation_rate: float = 0
    favorite_phrases: list[str] = Field(default_factory=list)
    discourse_markers: list[str] = Field(default_factory=list)
    sentence_openers: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class AnswerFeedback(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    answer: str = Field(min_length=1, max_length=40000)
    rating: Literal['up', 'down']
    reason: Literal['accurate', 'sounds_like_me', 'not_accurate', 'not_my_voice', 'too_long', 'too_slow', 'other']
    mode: str = ''
    provider: str = ''


class VoiceCandidate(BaseModel):
    session_id: str
    duration_seconds: float
    transcript_words: int
    words_per_minute: float | None = None
    score: float


class VoiceStatus(BaseModel):
    enabled: bool = False
    provider: str = 'disabled'
    consented: bool = False
    consented_at: datetime | None = None
    revoked_at: datetime | None = None
    reference_ready: bool = False
    reference_session_id: str | None = None
    reference_seconds: float = 0
    disclosure_version: str = '2.0'
    bridge_ready: bool = False
    bridge_busy: bool = False
    bridge_busy_seconds: float = 0
    bridge_request_id: str = ''
    cloud_voice_configured: bool = False
    voice_id: str = ''
    cloud_deletion_pending: bool = False
    cloud_deletion_error: str = ''


class VoicePrepareRequest(BaseModel):
    session_id: str
    confirm_voice_rights: bool
    provider: Literal['local', 'elevenlabs'] = 'local'
    reference_start_seconds: float = Field(default=5, ge=0, le=3600)
    reference_duration_seconds: float = Field(default=15, ge=3, le=180)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    speed: float = Field(default=1.0, ge=0.7, le=1.3)
    request_id: str = Field(default='', max_length=80, pattern=r'^[A-Za-z0-9_-]*$')
