import os
import tempfile
from pathlib import Path


TEST_ROOT = Path(tempfile.mkdtemp(prefix='here-i-am-tests-'))
LOCK_ROOT = Path(tempfile.mkdtemp(prefix='here-i-am-test-locks-', dir='/tmp'))
os.environ.update(
    {
        'DATA_ROOT': str(TEST_ROOT),
        'SESSIONS_DIR': str(TEST_ROOT / 'library' / 'sessions'),
        'CHROMA_DIR': str(TEST_ROOT / 'appdata' / 'chroma'),
        'LOGS_DIR': str(TEST_ROOT / 'appdata' / 'logs'),
        'TMP_DIR': str(TEST_ROOT / 'appdata' / 'tmp'),
        'JOBS_DIR': str(TEST_ROOT / 'appdata' / 'jobs'),
        'LOCKS_DIR': str(LOCK_ROOT),
        'EXPORTS_DIR': str(TEST_ROOT / 'appdata' / 'exports'),
        'BACKUP_ROOT': str(TEST_ROOT / 'backups'),
        'ARCHIVE_DIR': str(TEST_ROOT / 'library' / 'archive'),
        'PREFERENCES_PATH': str(TEST_ROOT / 'appdata' / 'preferences.json'),
        'FIDELITY_PROFILE_PATH': str(TEST_ROOT / 'appdata' / 'speaker_fingerprint.json'),
        'FEEDBACK_PATH': str(TEST_ROOT / 'appdata' / 'answer_feedback.jsonl'),
        'GENERATION_AUDIT_PATH': str(TEST_ROOT / 'appdata' / 'generation_audit.jsonl'),
        'VOICE_DIR': str(TEST_ROOT / 'appdata' / 'voice'),
        'LOCAL_BRIDGE_TOKEN': '',
        'OLLAMA_BASE_URL': 'http://127.0.0.1:1',
        'OLLAMA_CONTROL_URL': 'http://127.0.0.1:1',
        'VOICE_BRIDGE_URL': 'http://127.0.0.1:1',
        'LOCAL_WORKLOAD_LOCK_PATH': str(LOCK_ROOT / 'local-inference.lock'),
        'SPEAKERS_DIR': str(TEST_ROOT / 'appdata' / 'speakers'),
        'MAX_UPLOAD_SECONDS': '14400',
        'TRUSTED_HOSTS': 'localhost,127.0.0.1,testserver',
        'ALLOW_RUNTIME_CLOUD_KEY': 'true',
        'ALLOWED_OPENAI_MODELS': 'gpt-5.4-mini,gpt-5.4',
    }
)
