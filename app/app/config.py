from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    data_root: Path = Path('/data')
    ollama_api_base: str = 'http://host.docker.internal:11434'
    ollama_bridge_base: str = 'http://host.docker.internal:8765'
    chat_model: str = 'gemma4:e4b'
    embedding_model: str = 'embeddinggemma'
    whisper_model: str = 'small'
    chroma_collection: str = 'here_i_am_chunks'
    session_timezone: str = 'America/New_York'
    log_level: str = 'INFO'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
