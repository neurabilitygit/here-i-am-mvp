from __future__ import annotations

import json
import time
from pathlib import Path

import chromadb
from faster_whisper import WhisperModel
from chromadb.api.types import EmbeddingFunction

from config import settings
from services.jobs import job_manager
from services.ollama_client import ollama_client
from services.storage import (
    list_session_dirs,
    save_json,
    session_paths,
    update_processing_state,
)


VOICE_PROFILE_PATH = Path(settings.data_root) / "appdata" / "voice_profile.json"


class OllamaEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: list[str]) -> list[list[float]]:
        result = ollama_client.embed(input)
        if not isinstance(result, list):
            raise RuntimeError("Embedding function returned invalid result.")
        if result and isinstance(result[0], float):
            return [result]
        return result


_whisper_model = None
_chroma_client = None
_collection = None


def whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
        )
    return _whisper_model


def chroma_collection():
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_dir)
        _collection = _chroma_client.get_or_create_collection(
            name="here_i_am_chunks",
            embedding_function=OllamaEmbeddingFunction(),
            metadata={"description": "Transcript chunks for Here I Am"},
        )
    return _collection


def normalize_chroma_value(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return "" if value is None else value
    return str(value)


def transcript_plain_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.startswith("# ")).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def metadata_prompt(session_id: str, transcript: str) -> str:
    return f"""You are creating machine-readable metadata for a personal autobiography transcript.

Return strict JSON only.

Required top-level keys:
session_id, title, summary, topics, people, places, time_period, emotional_tone, content_type, notable_events, style_profile, style_exemplars

Rules:
- topics, people, places, notable_events must be arrays of strings.
- time_period may be either a string or an array of strings.
- style_profile must be an object with these keys:
  sentence_rhythm, vocabulary_style, rhetorical_habits, emotional_register, pacing_style, humor_style, certainty_style, storytelling_style, values_signals, recurring_concerns, conversational_stance, prosody_notes
- style_exemplars must be an object with these keys:
  explanatory, reflective, anecdotal, emphatic, conversational
- Each style_exemplars value should be a short quote-like excerpt or concise paraphrase representing the way the speaker talks.
- Be faithful to the transcript. Do not invent facts.
- When uncertain, be conservative.

Session ID: {session_id}

Transcript:
{transcript[:5000]}
"""


def load_voice_profile() -> dict:
    if VOICE_PROFILE_PATH.exists():
        return json.loads(VOICE_PROFILE_PATH.read_text(encoding="utf-8"))
    return {
        "profile_version": "1.0",
        "sessions_analyzed": 0,
        "sentence_rhythm": [],
        "vocabulary_style": [],
        "rhetorical_habits": [],
        "emotional_register": [],
        "pacing_style": [],
        "humor_style": [],
        "certainty_style": [],
        "storytelling_style": [],
        "values_signals": [],
        "recurring_concerns": [],
        "conversational_stance": [],
        "prosody_notes": [],
        "favorite_phrases": [],
        "style_exemplars": [],
        "last_updated_session_id": None,
    }


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        value = str(item).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def merge_voice_profile(profile: dict, metadata: dict, session_id: str) -> dict:
    style = metadata.get("style_profile", {}) or {}
    exemplars = metadata.get("style_exemplars", {}) or {}

    for key in [
        "sentence_rhythm",
        "vocabulary_style",
        "rhetorical_habits",
        "emotional_register",
        "pacing_style",
        "humor_style",
        "certainty_style",
        "storytelling_style",
        "values_signals",
        "recurring_concerns",
        "conversational_stance",
        "prosody_notes",
    ]:
        existing = profile.get(key, [])
        incoming = style.get(key, [])
        if isinstance(incoming, str):
            incoming = [incoming]
        elif not isinstance(incoming, list):
            incoming = [str(incoming)] if incoming else []
        profile[key] = dedupe_keep_order(existing + incoming)

    exemplar_items = []
    for label, value in exemplars.items():
        if value:
            exemplar_items.append(f"{label}: {value}")
    profile["style_exemplars"] = dedupe_keep_order(profile.get("style_exemplars", []) + exemplar_items)

    profile["sessions_analyzed"] = int(profile.get("sessions_analyzed", 0)) + 1
    profile["last_updated_session_id"] = session_id
    return profile


def save_voice_profile(profile: dict) -> None:
    VOICE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def voice_profile_text() -> str:
    profile = load_voice_profile()
    lines = []

    for key in [
        "sentence_rhythm",
        "vocabulary_style",
        "rhetorical_habits",
        "emotional_register",
        "pacing_style",
        "humor_style",
        "certainty_style",
        "storytelling_style",
        "values_signals",
        "recurring_concerns",
        "conversational_stance",
        "prosody_notes",
    ]:
        values = profile.get(key, [])
        if values:
            label = key.replace("_", " ")
            lines.append(f"{label}: {', '.join(values[:8])}")

    exemplars = profile.get("style_exemplars", [])
    if exemplars:
        lines.append("style exemplars:")
        for item in exemplars[:5]:
            lines.append(f"- {item}")

    return "\n".join(lines).strip()


def transcribe_unprocessed(job_id: str) -> None:
    sessions = [
        p for p in list_session_dirs()
        if session_paths(p)["audio"].exists() and not session_paths(p)["transcript"].exists()
    ]
    total = len(sessions)
    job_manager.update(job_id, status="running", total=total, message="Reading recordings")

    if total == 0:
        job_manager.update(
            job_id,
            status="done",
            message="No new recordings found",
            completed=True,
            result={"transcribed": 0},
        )
        return

    model = whisper_model()
    processed = 0

    for session in sessions:
        paths = session_paths(session)
        audio_path = paths["audio"]
        job_manager.update(
            job_id,
            current_file=audio_path.name,
            message=f"Transcribing {audio_path.name}",
            processed=processed,
        )

        segments, _info = model.transcribe(str(audio_path), vad_filter=True)
        segments = list(segments)
        transcript_text = " ".join(segment.text.strip() for segment in segments).strip()
        transcript_body = f"# Transcript\n\nSession: {session.name}\n\n{transcript_text}\n"
        paths["transcript"].write_text(transcript_body, encoding="utf-8")

        update_processing_state(session, transcribed=True)
        processed += 1

        job_manager.update(
            job_id,
            message=f"Saved transcript for {session.name}",
            processed=processed,
            current_file=audio_path.name,
        )

    job_manager.update(
        job_id,
        status="done",
        message="All recordings have been transcribed",
        processed=processed,
        completed=True,
        result={"transcribed": processed},
    )


def analyze_unprocessed(job_id: str) -> None:
    sessions = [
        p
        for p in list_session_dirs()
        if session_paths(p)["transcript"].exists() and not session_paths(p)["metadata"].exists()
    ]
    total = len(sessions)
    job_manager.update(job_id, status="running", total=total, message="Reading transcripts")

    if total == 0:
        job_manager.update(
            job_id,
            status="done",
            message="No new transcripts found",
            completed=True,
            result={"analyzed": 0, "embedded_chunks": 0},
        )
        return

    collection = chroma_collection()
    processed = 0
    embedded_chunks = 0

    for session in sessions:
        paths = session_paths(session)
        transcript = transcript_plain_text(paths["transcript"])

        job_manager.update(
            job_id,
            current_file=paths["transcript"].name,
            message=f"Analyzing {paths['transcript'].name}",
            processed=processed,
        )

        try:
            t0 = time.time()
            metadata = ollama_client.generate_json(metadata_prompt(session.name, transcript))
            print(f"[TIMING] analysis_generate session={session.name} elapsed={time.time()-t0:.2f}s")
        except Exception as exc:
            job_manager.update(
                job_id,
                status="error",
                message=f"Analysis failed for {session.name}: {exc}",
                processed=processed,
                completed=True,
            )
            return

        metadata["session_id"] = session.name
        metadata["metadata_version"] = settings.metadata_version
        metadata["audio_path"] = str(paths["audio"])
        metadata["transcript_path"] = str(paths["transcript"])
        save_json(paths["metadata"], metadata)

        profile = load_voice_profile()
        profile = merge_voice_profile(profile, metadata, session.name)
        save_voice_profile(profile)

        chunks = chunk_text(transcript, settings.chunk_size_chars, settings.chunk_overlap_chars)
        chunk_records = []
        ids = []
        documents = []
        metadatas = []

        for index, chunk in enumerate(chunks):
            chunk_id = f"{session.name}::chunk::{index:04d}"
            chunk_meta = {
                "session_id": normalize_chroma_value(session.name),
                "chunk_index": index,
                "title": normalize_chroma_value(metadata.get("title", session.name)),
                "summary": normalize_chroma_value(metadata.get("summary", "")),
                "topics": normalize_chroma_value(metadata.get("topics", [])),
                "people": normalize_chroma_value(metadata.get("people", [])),
                "places": normalize_chroma_value(metadata.get("places", [])),
                "content_type": normalize_chroma_value(metadata.get("content_type", "autobiography")),
                "time_period": normalize_chroma_value(metadata.get("time_period", "")),
                "sentence_rhythm": normalize_chroma_value((metadata.get("style_profile", {}) or {}).get("sentence_rhythm", "")),
                "rhetorical_habits": normalize_chroma_value((metadata.get("style_profile", {}) or {}).get("rhetorical_habits", "")),
                "conversational_stance": normalize_chroma_value((metadata.get("style_profile", {}) or {}).get("conversational_stance", "")),
            }
            chunk_records.append({"id": chunk_id, "text": chunk, "metadata": chunk_meta})
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(chunk_meta)

        if ids:
            try:
                collection.delete(where={"session_id": session.name})
            except Exception:
                pass
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
            embedded_chunks += len(ids)

        with paths["chunks"].open("w", encoding="utf-8") as fh:
            for record in chunk_records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        update_processing_state(session, analyzed=True, embedded=True)
        processed += 1

        job_manager.update(
            job_id,
            current_file=paths["transcript"].name,
            message=f"Embedded {len(ids)} chunks for {session.name}",
            processed=processed,
        )

    job_manager.update(
        job_id,
        status="done",
        message="All new transcripts have been analyzed and embedded",
        processed=processed,
        completed=True,
        result={"analyzed": processed, "embedded_chunks": embedded_chunks},
    )


def classify_question_mode(question: str) -> str:
    prompt = f"""Classify the user's question.

Return only one word:
PERSONAL
GENERAL
or
HYBRID

Use PERSONAL when the question is about the user's life, memories, recordings, views, experiences, preferences, family, work, history, or anything that should be answered mainly from the personal transcript library.

Use GENERAL when the question asks for general knowledge, explanation, science, history, literature, philosophy, or abstract concepts that do not depend on the personal transcript library.

Use HYBRID when the question asks for both:
- a general explanation or outside knowledge
and
- the user's views, experiences, style, or personal framing.

If the question requires factual explanation that is unlikely to appear in personal recordings, choose GENERAL.
If it asks about beliefs, memories, experiences, or opinions, choose PERSONAL.
If it asks for both explanation and personal framing, choose HYBRID.

Question:
{question}
"""
    raw = ollama_client.analyze(prompt).strip().upper()
    if "HYBRID" in raw:
        return "HYBRID"
    if "PERSONAL" in raw:
        return "PERSONAL"
    return "GENERAL"


def answer_general_question(question: str) -> str:
    style_profile = voice_profile_text()

    system = (
        "You are a helpful assistant answering a general knowledge question. "
        "You may be lightly influenced by the voice profile for phrasing and rhythm, "
        "but do not pretend to have personal memories or lived experience unless the question is actually personal. "
        "Do not force autobiographical framing. "
        "Answer clearly and directly."
    )
    user = f"Question: {question}\n\nVoice profile:\n{style_profile}"
    prompt = f"{system}\n\n{user}"
    return ollama_client.chat(prompt)


def answer_hybrid_question(question: str) -> str:
    docs, metas = query_context(question)
    context_lines = []

    for idx, (doc, meta) in enumerate(zip(docs, metas), start=1):
        context_lines.append(
            f"Context {idx} | session={meta.get('session_id','')} | title={meta.get('title','')} | topics={meta.get('topics','')} | rhythm={meta.get('sentence_rhythm','')} | stance={meta.get('conversational_stance','')}\n{doc}"
        )

    context = "\n\n".join(context_lines)
    style_profile = voice_profile_text()

    system = (
        "You are answering a hybrid question that requires both general knowledge and the user's personal material. "
        "When the user says 'you', 'your', or similar words in a personal sense, they are referring to the recorded person. "
        "Use the retrieved personal transcripts as grounded evidence about that person. "
        "Also use your general knowledge where needed to explain concepts clearly. "
        "Do not quote passages directly. Do not mention retrieval or source passages. "
        "Do not invent autobiographical facts. "
        "If a biographical fact is not explicit in the personal background, say that the recordings do not clearly state it. "
        "Blend outside explanation with the user's perspective in a natural, disciplined way."
    )
    user = f"Question: {question}\n\nVoice profile:\n{style_profile}\n\nPersonal background:\n{context}"
    prompt = f"{system}\n\n{user}"
    return ollama_client.chat(prompt)


def query_context(question: str, n_results: int | None = None) -> tuple[list[str], list[dict]]:
    collection = chroma_collection()
    results = collection.query(
        query_texts=[question],
        n_results=n_results or settings.max_chat_context_chunks,
    )
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    return docs, metadatas


def answer_question(question: str) -> str:
    t0 = time.time()

    mode = classify_question_mode(question)
    print(f"[TIMING] question_mode={mode}")

    if mode == "GENERAL":
        t1 = time.time()
        response = answer_general_question(question)
        t2 = time.time()
        print(f"[TIMING] general_generation={t2-t1:.2f}s total={t2-t0:.2f}s")
        return response

    if mode == "HYBRID":
        t1 = time.time()
        response = answer_hybrid_question(question)
        t2 = time.time()
        print(f"[TIMING] hybrid_total={t2-t1:.2f}s overall={t2-t0:.2f}s")
        return response

    t1 = time.time()
    docs, metas = query_context(question)
    t2 = time.time()

    if not docs:
        print("[ROUTER] fallback_to_general")
        t3 = time.time()
        response = answer_general_question(question)
        t4 = time.time()
        print(f"[TIMING] fallback_general={t4-t3:.2f}s total={t4-t0:.2f}s")
        return response

    context_lines = []

    for idx, (doc, meta) in enumerate(zip(docs, metas), start=1):
        context_lines.append(
            f"Context {idx} | session={meta.get('session_id','')} | title={meta.get('title','')} | topics={meta.get('topics','')} | rhythm={meta.get('sentence_rhythm','')} | stance={meta.get('conversational_stance','')}\n{doc}"
        )

    context = "\n\n".join(context_lines)
    t3 = time.time()

    style_profile = voice_profile_text()

    system = (
        "You are answering questions as the person whose recordings and memories are stored in this system. "
        "When the user says 'you', 'your', or similar words, they are referring to the recorded person, not to an AI assistant. "
        "Answer using only retrieved personal transcripts and the learned voice profile. "
        "Do not quote passages directly. Do not mention retrieval or source passages. "
        "Do not invent or infer autobiographical facts. "
        "For biographical facts such as birthplace, education, family details, or life events, answer only if the fact is explicit in the retrieved material. "
        "If the retrieved material does not clearly state the answer, say that you do not think you have said that in your recordings yet. "
        "Default to a neutral helpful style, but let the sentence rhythm, phrasing, and rhetorical habits be influenced by the voice profile when doing so remains natural. "
        "Do not overdo imitation. Preserve factual grounding."
    )
    user = f"Question: {question}\n\nVoice profile:\n{style_profile}\n\nRelevant background:\n{context}"
    prompt = f"{system}\n\n{user}"

    response = ollama_client.chat(prompt)
    t4 = time.time()

    print(
        f"[TIMING] personal_retrieval={t2-t1:.2f}s context_build={t3-t2:.2f}s generation={t4-t3:.2f}s total={t4-t0:.2f}s"
    )

    return response
