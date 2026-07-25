from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from config import settings
from models.schemas import ReconciliationIssue, ReconciliationReport, SessionDetail, SessionSummary
from services.storage import atomic_write_text, load_json, safe_session_dir, session_paths


def _modified_at(paths: list[Path]):
    values = [path.stat().st_mtime for path in paths if path.exists()]
    return datetime.fromtimestamp(max(values), tz=timezone.utc) if values else None


def _recorded_at(session_path: Path) -> str:
    name = session_path.name
    return name[:10] if len(name) >= 10 and name[4] == '-' and name[7] == '-' else ''


def _is_still_sealed(state: dict) -> bool:
    unlock_at = state.get('unlock_at')
    if not unlock_at:
        return False
    try:
        return datetime.fromisoformat(unlock_at) > datetime.now(timezone.utc)
    except ValueError:
        return False


def session_summary(session_path: Path) -> SessionSummary:
    paths = session_paths(session_path)
    state = load_json(paths['state']) if paths['state'].exists() else {}
    metadata = load_json(paths['metadata']) if paths['metadata'].exists() else {}
    return SessionSummary(
        session_id=session_path.name,
        title=str(metadata.get('title') or session_path.name),
        recorded=paths['audio'].exists(),
        transcribed=paths['transcript'].exists(),
        analyzed=paths['metadata'].exists() and bool(state.get('analyzed', False)),
        embedded=paths['chunks'].exists() and bool(state.get('embedded', False)),
        audio_bytes=paths['audio'].stat().st_size if paths['audio'].exists() else 0,
        transcript_bytes=paths['transcript'].stat().st_size if paths['transcript'].exists() else 0,
        updated_at=_modified_at(list(paths.values())),
        recording_mode=state.get('recording_mode', 'solo'),
        speaker_review_status=state.get('speaker_review_status', 'not_required'),
        speaker_count=int(state.get('speaker_count', 1)),
        recorded_at=_recorded_at(session_path),
        time_period=metadata.get('time_period') or '',
        emotional_tone=metadata.get('emotional_tone') or [],
        topics=metadata.get('topics') or [],
        notable_events=metadata.get('notable_events') or [],
        sealed=_is_still_sealed(state),
        unlock_at=state.get('unlock_at'),
    )


def _all_session_summaries() -> list[SessionSummary]:
    root = Path(settings.sessions_dir)
    if not root.exists():
        return []
    return [session_summary(path) for path in sorted(root.iterdir(), reverse=True) if path.is_dir()]


def list_sessions() -> list[SessionSummary]:
    return [summary for summary in _all_session_summaries() if not summary.sealed]


def sealed_sessions() -> list[SessionSummary]:
    return [summary for summary in _all_session_summaries() if summary.sealed]


def on_this_day_sessions(today: date | None = None) -> list[SessionSummary]:
    reference = today or date.today()
    month_day = (reference.month, reference.day)
    matches = []
    for summary in list_sessions():
        if not summary.recorded_at or summary.sealed:
            continue
        try:
            recorded = date.fromisoformat(summary.recorded_at)
        except ValueError:
            continue
        if recorded.year != reference.year and (recorded.month, recorded.day) == month_day:
            matches.append(summary)
    return matches


def days_since_last_recording() -> int | None:
    sessions = [summary for summary in list_sessions() if summary.recorded_at]
    if not sessions:
        return None
    most_recent = sessions[0]
    try:
        recorded = date.fromisoformat(most_recent.recorded_at)
    except ValueError:
        return None
    return (date.today() - recorded).days


def get_session(session_id: str, include_transcript: bool = True) -> SessionDetail:
    path = safe_session_dir(session_id)
    if not path.exists():
        raise FileNotFoundError('Session does not exist')
    summary = session_summary(path)
    if summary.sealed:
        return SessionDetail(**summary.model_dump(), state={}, metadata={}, transcript=None)
    paths = session_paths(path)
    return SessionDetail(
        **summary.model_dump(),
        state=load_json(paths['state']) if paths['state'].exists() else {},
        metadata=load_json(paths['metadata']) if paths['metadata'].exists() else {},
        transcript=paths['transcript'].read_text(encoding='utf-8') if include_transcript and paths['transcript'].exists() else None,
    )


def reconciliation_report() -> ReconciliationReport:
    issues: list[ReconciliationIssue] = []
    sessions = list_sessions()
    for summary in sessions:
        path = safe_session_dir(summary.session_id)
        state_path = session_paths(path)['state']
        state = load_json(state_path) if state_path.exists() else {}
        if not state_path.exists():
            issues.append(ReconciliationIssue(session_id=summary.session_id, code='missing_state', detail='processing_state.json is missing'))
        comparisons = {
            'recorded': summary.recorded,
            'transcribed': summary.transcribed,
            'analyzed': summary.analyzed,
            'embedded': summary.embedded,
        }
        for key, actual in comparisons.items():
            declared = bool(state.get(key, False))
            if declared != actual:
                issues.append(
                    ReconciliationIssue(
                        session_id=summary.session_id,
                        code=f'{key}_state_mismatch',
                        detail=f'state={declared}, artifact_present={actual}',
                    )
                )
        if summary.analyzed and not summary.embedded:
            issues.append(
                ReconciliationIssue(
                    session_id=summary.session_id,
                    code='analysis_incomplete',
                    detail='Metadata exists but portable chunk output is missing',
                )
            )
        active_version = str(state.get('active_content_version') or '')
        if state.get('embedded', False) and active_version:
            metadata_path = session_paths(path)['metadata']
            chunks_path = session_paths(path)['chunks']
            try:
                metadata = load_json(metadata_path)
                if str(metadata.get('content_version') or '') != active_version:
                    issues.append(ReconciliationIssue(
                        session_id=summary.session_id,
                        code='metadata_version_mismatch',
                        detail='metadata.json does not match the activated content version',
                    ))
                chunk_versions = {
                    str((json.loads(line).get('metadata') or {}).get('content_version') or '')
                    for line in chunks_path.read_text(encoding='utf-8').splitlines()
                    if line.strip()
                }
                if chunk_versions != {active_version}:
                    issues.append(ReconciliationIssue(
                        session_id=summary.session_id,
                        code='chunk_version_mismatch',
                        detail='chunks.jsonl does not match the activated content version',
                    ))
            except (OSError, json.JSONDecodeError):
                issues.append(ReconciliationIssue(
                    session_id=summary.session_id,
                    code='active_artifact_unreadable',
                    detail='An activated metadata or chunk artifact is unreadable',
                ))

    # Chroma is append-only. Reconciliation verifies that every activated
    # version is represented without treating preserved historical vectors as
    # orphans or deleting anything.
    try:
        from services.pipeline import chroma_collection

        vector_data = chroma_collection().get(include=['metadatas'])
        vector_versions: dict[tuple[str, str], int] = {}
        for metadata in vector_data.get('metadatas') or []:
            metadata = metadata or {}
            key = (
                str(metadata.get('session_id', '')),
                str(metadata.get('content_version') or 'legacy'),
            )
            vector_versions[key] = vector_versions.get(key, 0) + 1
        for summary in sessions:
            path = safe_session_dir(summary.session_id)
            state_path = session_paths(path)['state']
            state = load_json(state_path) if state_path.exists() else {}
            if not state.get('embedded', False):
                continue
            version = str(state.get('active_content_version') or 'legacy')
            if not vector_versions.get((summary.session_id, version)):
                issues.append(ReconciliationIssue(
                    session_id=summary.session_id,
                    code='missing_active_vectors',
                    detail=f'No Chroma records exist for activated version {version}',
                ))
    except Exception as exc:
        issues.append(ReconciliationIssue(
            session_id='system',
            code='vector_reconciliation_unavailable',
            detail=f'Chroma could not be inspected: {type(exc).__name__}',
        ))
    return ReconciliationReport(
        checked_sessions=len(sessions),
        issue_count=len(issues),
        issues=issues,
        repair_applied=False,
    )


def build_session_export(session_id: str) -> Path:
    session = safe_session_dir(session_id)
    if not session.exists():
        raise FileNotFoundError('Session does not exist')
    Path(settings.exports_dir).mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'{session_id}-', suffix='.zip', dir=settings.exports_dir)
    Path(name).unlink(missing_ok=True)
    # mkstemp reserves the unique name; zipfile recreates it.
    try:
        import os
        os.close(fd)
    except OSError:
        pass
    export_path = Path(name)
    with zipfile.ZipFile(export_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(session.rglob('*')):
            if path.is_file() and not path.name.startswith('._'):
                archive.write(path, arcname=f'{session.name}/{path.relative_to(session)}')
    return export_path


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def create_structured_backup(progress: Callable[[int, int, str], None] | None = None) -> dict:
    root = Path(settings.data_root)
    backup_root = Path(settings.backup_root)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    target = backup_root / stamp
    target.mkdir(parents=True, exist_ok=False)
    manifest: list[dict] = []

    def source_files(source_root: Path) -> list[Path]:
        if not source_root.exists():
            return []
        files: list[Path] = []
        for source in sorted(source_root.rglob('*')):
            if source.name.startswith('._'):
                continue
            try:
                if source.is_file():
                    files.append(source)
            except OSError:
                continue
        return files

    authoritative_files = [
        *source_files(Path(settings.sessions_dir)),
        *source_files(Path(settings.archive_dir)),
    ]
    appdata = root / 'appdata'
    excluded_roots = {
        Path(settings.chroma_dir).resolve(),
        backup_root.resolve(),
        Path(settings.tmp_dir).resolve(),
        Path(settings.locks_dir).resolve(),
        Path(settings.exports_dir).resolve(),
        (appdata / 'models').resolve(),
    }
    appdata_files: list[Path] = []
    for source in source_files(appdata):
        try:
            resolved = source.resolve()
            if any(resolved == excluded or excluded in resolved.parents for excluded in excluded_roots):
                continue
        except OSError:
            continue
        appdata_files.append(source)

    from services.pipeline import chroma_collection

    collection = chroma_collection()
    vector_count = collection.count()
    total_items = len(authoritative_files) + len(appdata_files) + vector_count
    processed = 0

    def report(message: str) -> None:
        if progress:
            progress(processed, total_items, message)

    for source in authoritative_files:
        # ExFAT/iCloud may leave unreadable AppleDouble sidecars. Filter by
        # supported filename before stat-ing and treat filesystem artifacts as
        # non-authoritative rather than allowing a backup to fail.
        relative = source.relative_to(root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        digest = _sha256_file(destination)
        manifest.append({'path': str(relative), 'bytes': destination.stat().st_size, 'sha256': digest})
        processed += 1
        report(f'Copied {relative}')
    for source in appdata_files:
        relative = source.relative_to(root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest.append({'path': str(relative), 'bytes': destination.stat().st_size, 'sha256': _sha256_file(destination)})
        processed += 1
        report(f'Copied {relative}')

    vector_export = target / 'appdata' / 'chroma-export.jsonl'
    vector_export.parent.mkdir(parents=True, exist_ok=True)
    with vector_export.open('w', encoding='utf-8') as handle:
        page_size = 128
        for offset in range(0, vector_count, page_size):
            vector_data = collection.get(
                limit=min(page_size, vector_count - offset),
                offset=offset,
                include=['documents', 'metadatas', 'embeddings'],
            )
            vector_documents = vector_data.get('documents') or []
            vector_metadatas = vector_data.get('metadatas') or []
            vector_embeddings = vector_data.get('embeddings')
            for index, identifier in enumerate(vector_data.get('ids') or []):
                embedding = vector_embeddings[index]
                record = {
                    'id': identifier,
                    'document': vector_documents[index],
                    'metadata': vector_metadatas[index],
                    'embedding': embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed += 1
            report(f'Exported {min(offset + page_size, vector_count)} of {vector_count} Chroma records')
        handle.flush()
        import os
        os.fsync(handle.fileno())
    manifest.append({
        'path': str(vector_export.relative_to(target)),
        'bytes': vector_export.stat().st_size,
        'sha256': _sha256_file(vector_export),
    })
    manifest_path = target / 'manifest.json'
    try:
        same_volume = root.stat().st_dev == backup_root.stat().st_dev
    except OSError:
        same_volume = root.resolve() in backup_root.resolve().parents or backup_root.resolve() == root.resolve()
    atomic_write_text(manifest_path, json.dumps({
        'created_at': datetime.now(timezone.utc).isoformat(),
        'backup_kind': 'full-rebuildable',
        'chroma_collection': settings.chroma_collection,
        'same_volume_as_source': same_volume,
        'files': manifest,
    }, indent=2))
    return {
        'backup_id': stamp,
        'backup_kind': 'full-rebuildable',
        'files': len(manifest),
        'bytes': sum(item['bytes'] for item in manifest),
        'same_volume_as_source': same_volume,
        'warning': 'Configure BACKUP_ROOT on another encrypted volume for disaster recovery.' if same_volume else '',
    }
