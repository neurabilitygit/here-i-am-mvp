from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Here I Am'
    app_build_commit: str = 'unknown'
    app_build_date: str = ''
    host: str = '0.0.0.0'
    port: int = 8787
    data_root: str = '/data'
    sessions_dir: str = '/data/library/sessions'
    chroma_dir: str = '/data/appdata/chroma'
    logs_dir: str = '/data/appdata/logs'
    tmp_dir: str = '/data/appdata/tmp'
    jobs_dir: str = '/data/appdata/jobs'
    locks_dir: str = '/data/appdata/locks'
    exports_dir: str = '/data/appdata/exports'
    backup_root: str = '/data/appdata/backups'
    archive_dir: str = '/data/library/archive'
    preferences_path: str = '/data/appdata/preferences.json'
    fidelity_profile_path: str = '/data/appdata/speaker_fingerprint.json'
    feedback_path: str = '/data/appdata/answer_feedback.jsonl'
    generation_audit_path: str = '/data/appdata/generation_audit.jsonl'
    activity_event_path: str = '/data/appdata/logs/activity_events.jsonl'
    voice_dir: str = '/data/appdata/voice'
    speakers_dir: str = '/data/appdata/speakers'
    ollama_base_url: str = 'http://host.docker.internal:11434'
    ollama_control_url: str = 'http://host.docker.internal:8778'
    ollama_chat_model: str = 'gemma4:e4b'
    ollama_analysis_model: str = 'gemma4:e4b'
    ollama_embedding_model: str = 'embeddinggemma'
    ollama_keep_alive: str = '30m'
    ollama_chat_max_tokens: int = 640
    ollama_analysis_max_tokens: int = 3072
    text_provider: Literal['local', 'openai'] = 'local'
    openai_api_key: str = ''
    openai_api_key_file: str = ''
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_model: str = 'gpt-5.4-mini'
    allowed_openai_models: str = 'gpt-5.4-mini,gpt-5.4'
    allow_runtime_cloud_key: bool = False
    provider_stream_heartbeat_seconds: int = 15
    provider_connect_timeout_seconds: int = 10
    provider_read_timeout_seconds: int = 300
    cloud_store_responses: bool = False
    voice_provider: str = 'disabled'
    voice_bridge_url: str = 'http://host.docker.internal:8779'
    local_bridge_token: str = 'here-i-am-local-v1'
    auth_passphrase_hash_file: str = ''
    auth_tokens_path: str = '/data/appdata/auth_tokens.json'
    auth_token_ttl_seconds: int = 2_592_000
    auth_max_failed_attempts: int = 10
    auth_lockout_seconds: int = 900
    voice_host_data_root: str = '/Volumes/Personal/here-i-am'
    elevenlabs_api_key: str = ''
    elevenlabs_voice_id: str = ''
    elevenlabs_model: str = 'eleven_multilingual_v2'
    speaker_diarization_provider: Literal['openai', 'disabled'] = 'openai'
    speaker_diarization_model: str = 'gpt-4o-transcribe-diarize'
    speaker_diarization_timeout_seconds: int = 900
    speaker_reference_seconds: int = 8
    avatar_image_model: str = 'gpt-image-2'
    avatar_image_quality: Literal['low', 'medium', 'high'] = 'medium'
    max_avatar_upload_bytes: int = 20 * 1024 * 1024
    whisper_model: str = 'base'
    chroma_collection: str = 'here_i_am_chunks'
    chroma_migration_collection: str = 'here_i_am_chunks_v2'
    retrieval_seed_chunks: int = 4
    retrieval_candidate_chunks: int = 12
    max_chat_context_chunks: int = 6
    max_context_chunk_chars: int = 1200
    chat_temperature: float = 0.2
    voice_request_timeout_seconds: int = 60
    voice_batch_timeout_seconds: int = 900
    chunk_size_chars: int = 1200
    chunk_overlap_chars: int = 200
    chunk_size_words: int = 220
    chunk_overlap_words: int = 40
    retrieval_max_distance: float | None = None
    metadata_version: str = '2.0'
    app_timezone: str = 'America/New_York'
    max_upload_bytes: int = 536_870_912
    max_upload_seconds: int = 14_400
    api_docs_enabled: bool = False
    cors_origins: str = 'http://localhost:8787,http://127.0.0.1:8787'
    trusted_hosts: str = 'localhost,127.0.0.1,testserver,host.docker.internal'
    log_level: str = 'INFO'
    jsonl_rotate_bytes: int = 10 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(',') if value.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [value.strip() for value in self.trusted_hosts.split(',') if value.strip()]

    @property
    def allowed_openai_model_list(self) -> list[str]:
        configured = [value.strip() for value in self.allowed_openai_models.split(',') if value.strip()]
        return list(dict.fromkeys([self.openai_model, *configured]))

    @property
    def data_root_path(self) -> Path:
        return Path(self.data_root)


settings = Settings()
