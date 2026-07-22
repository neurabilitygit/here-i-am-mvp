from __future__ import annotations

import json
import math
import re
import statistics
import subprocess
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from models.schemas import AnswerFeedback, SpeakerFingerprint
from services.jsonl_store import append_jsonl
from services.storage import atomic_write_text, list_session_dirs, load_json, session_paths


_feedback_lock = threading.Lock()
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')
MARKERS = ['you know', 'I mean', 'the thing is', 'in other words', 'as I recall', 'I think', 'I remember', 'well', 'so', 'now', 'actually']
STOP_OPENERS = {'the', 'a', 'an', 'and', 'but', 'or', 'this', 'that', 'it'}


def _plain_transcript(path: Path) -> str:
    return '\n'.join(
        line for line in path.read_text(encoding='utf-8').splitlines()
        if not line.startswith('# ') and not line.startswith('Session:')
    ).strip()


def _audio_duration(path: Path) -> float | None:
    completed = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return float(json.loads(completed.stdout)['format']['duration'])
    except Exception:
        return None


def build_speaker_fingerprint() -> SpeakerFingerprint:
    texts: list[str] = []
    total_audio_seconds = 0.0
    timed_words = 0
    sentence_lengths: list[int] = []
    phrase_counter: Counter[str] = Counter()
    opener_counter: Counter[str] = Counter()
    marker_counter: Counter[str] = Counter()

    for session in list_session_dirs():
        paths = session_paths(session)
        if not paths['transcript'].exists():
            continue
        state = load_json(paths['state']) if paths['state'].exists() else {}
        recording_mode = state.get('recording_mode', 'solo')
        conversation_seconds = 0.0
        if recording_mode == 'conversation':
            if state.get('speaker_review_status') != 'complete' or not paths['memory_units'].exists():
                continue
            units = [
                json.loads(line)
                for line in paths['memory_units'].read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
            text = ' '.join(str(unit.get('subject_evidence') or '').strip() for unit in units).strip()
            conversation_seconds = sum(
                max(0.0, float(unit.get('end', 0)) - float(unit.get('start', 0)))
                for unit in units
            )
        else:
            text = _plain_transcript(paths['transcript'])
        if not text:
            continue
        texts.append(text)
        words = [word.lower() for word in WORD_RE.findall(text)]
        if recording_mode == 'conversation' and conversation_seconds >= 10:
            total_audio_seconds += conversation_seconds
            timed_words += len(words)
        elif recording_mode != 'conversation' and paths['audio'].exists():
            duration = _audio_duration(paths['audio'])
            if duration and duration >= 10:
                total_audio_seconds += duration
                timed_words += len(words)
        for sentence in SENTENCE_RE.split(text):
            values = [word.lower() for word in WORD_RE.findall(sentence)]
            if values:
                sentence_lengths.append(len(values))
                opener = ' '.join(values[:2]) if len(values) > 1 else values[0]
                if values[0] not in STOP_OPENERS:
                    opener_counter[opener] += 1
        for size in (2, 3):
            for index in range(len(words) - size + 1):
                phrase = ' '.join(words[index:index + size])
                if words[index] not in STOP_OPENERS and len(set(words[index:index + size])) > 1:
                    phrase_counter[phrase] += 1
        lowered = text.lower()
        for marker in MARKERS:
            marker_counter[marker] += lowered.count(marker)

    combined = '\n'.join(texts)
    all_words = WORD_RE.findall(combined)
    sentences = [value for value in SENTENCE_RE.split(combined) if WORD_RE.search(value)]
    contractions = sum("'" in word for word in all_words)
    fingerprint = SpeakerFingerprint(
        transcript_count=len(texts),
        audio_hours=round(total_audio_seconds / 3600, 3),
        word_count=len(all_words),
        average_sentence_words=round(statistics.mean(sentence_lengths), 2) if sentence_lengths else 0,
        sentence_length_variation=round(statistics.pstdev(sentence_lengths), 2) if len(sentence_lengths) > 1 else 0,
        average_words_per_minute=round(timed_words / (total_audio_seconds / 60), 1) if total_audio_seconds else None,
        contraction_rate=round(contractions / max(1, len(all_words)), 4),
        question_rate=round(combined.count('?') / max(1, len(sentences)), 4),
        exclamation_rate=round(combined.count('!') / max(1, len(sentences)), 4),
        favorite_phrases=[phrase for phrase, count in phrase_counter.most_common(18) if count >= 3][:10],
        discourse_markers=[marker for marker, count in marker_counter.most_common() if count >= 2],
        sentence_openers=[value for value, count in opener_counter.most_common(10) if count >= 2],
    )
    atomic_write_text(Path(settings.fidelity_profile_path), fingerprint.model_dump_json(indent=2))
    return fingerprint


def load_speaker_fingerprint() -> SpeakerFingerprint:
    path = Path(settings.fidelity_profile_path)
    if path.exists():
        try:
            return SpeakerFingerprint.model_validate_json(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return build_speaker_fingerprint()


def fingerprint_prompt() -> str:
    profile = load_speaker_fingerprint()
    return (
        f"Measured from {profile.transcript_count} reviewed transcripts and {profile.audio_hours:.2f} hours of audio: "
        f"average sentence length {profile.average_sentence_words:.1f} words (variation {profile.sentence_length_variation:.1f}); "
        f"natural speaking pace approximately {profile.average_words_per_minute or 'unknown'} words per minute; "
        f"contraction rate {profile.contraction_rate:.3f}; question rate {profile.question_rate:.3f}.\n"
        f"Recurring phrases: {', '.join(profile.favorite_phrases) or 'not enough evidence'}.\n"
        f"Discourse markers: {', '.join(profile.discourse_markers) or 'not enough evidence'}.\n"
        f"Common openings: {', '.join(profile.sentence_openers) or 'not enough evidence'}."
    )


def save_answer_feedback(feedback: AnswerFeedback) -> dict:
    record = feedback.model_dump(mode='json')
    record['created_at'] = datetime.now(timezone.utc).isoformat()
    path = Path(settings.feedback_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _feedback_lock:
        append_jsonl(path, record)
    return {'status': 'saved'}
