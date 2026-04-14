from pathlib import Path
import os


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


DATA_ROOT = Path(env("DATA_ROOT", "/data")).resolve()
LIBRARY_ROOT = DATA_ROOT / "library"
SESSIONS_ROOT = LIBRARY_ROOT / "sessions"
APPDATA_ROOT = DATA_ROOT / "appdata"
CHROMA_ROOT = APPDATA_ROOT / "chroma"
LOG_ROOT = APPDATA_ROOT / "logs"
TMP_ROOT = APPDATA_ROOT / "tmp"
STATE_ROOT = APPDATA_ROOT / "state"
UPLOADS_ROOT = TMP_ROOT / "uploads"

OLLAMA_API_BASE = env("OLLAMA_API_BASE", "http://host.docker.internal:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", "embeddinggemma")
OLLAMA_HOST_HELPER = env("OLLAMA_HOST_HELPER", "http://host.docker.internal:8765")
WHISPER_MODEL = env("WHISPER_MODEL", "base")
CHROMA_COLLECTION = env("CHROMA_COLLECTION", "here_i_am")
CHUNK_SIZE = int(env("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(env("CHUNK_OVERLAP", "200"))


for path in [
    DATA_ROOT,
    LIBRARY_ROOT,
    SESSIONS_ROOT,
    APPDATA_ROOT,
    CHROMA_ROOT,
    LOG_ROOT,
    TMP_ROOT,
    STATE_ROOT,
    UPLOADS_ROOT,
]:
    path.mkdir(parents=True, exist_ok=True)
