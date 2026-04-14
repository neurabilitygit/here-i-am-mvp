from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Here I Am'
    host: str = '0.0.0.0'
    port: int = 8787
    data_root: str = '/data'
    sessions_dir: str = '/data/library/sessions'
    chroma_dir: str = '/data/appdata/chroma'
    logs_dir: str = '/data/appdata/logs'
    tmp_dir: str = '/data/appdata/tmp'
    ollama_base_url: str = 'http://host.docker.internal:11434'
    ollama_control_url: str = 'http://host.docker.internal:8778'
    ollama_chat_model: str = 'gemma4:e4b'
    ollama_analysis_model: str = 'gemma4:e4b'
    ollama_embedding_model: str = 'embeddinggemma'
    whisper_model: str = 'base'
    max_chat_context_chunks: int = 3
    chat_temperature: float = 0.2
    chunk_size_chars: int = 700
    chunk_overlap_chars: int = 100
    metadata_version: str = '1.0'
    app_timezone: str = 'America/New_York'

    @property
    def data_root_path(self) -> Path:
        return Path(self.data_root)


settings = Settings()
