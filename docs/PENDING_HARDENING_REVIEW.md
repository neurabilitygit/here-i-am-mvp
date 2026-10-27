# Pending Phase 1–5 hardening

Recorded on 2026-10-26. This branch preserves earlier implementation work;
it is not a deployment approval or an implementation of the new local-performance plan.

## Source and deployment

- Operational checkout: `/Volumes/Personal/here-i-am-mvp`.
- Production baseline at review: `3cc38695435030207f9670ddc164198293937641`,
  branch `feature/engagement-features`.
- Pending source: `/Users/ericbass/Documents/Here-I-Am`, branch `codex/phase-1-5`.
- GitHub main remains an older baseline; do not deploy it merely because it is named main.
- Keep ExFAT and the existing storage locations. No APFS migration is planned.
- Never delete existing Chroma records.

## Preserved changes

1. Recording durability: retain uploaded source audio after conversion failures,
   retry validation, track upload status, and retry transient state-file reads.
2. Library safety: serialize protected mutations and backups, strengthen durable
   writes, and fail closed for invalid sealed-memory dates.
3. Conversation handling: explicit cloud consent, editable speaker-labeled
   transcripts, and revocation of reusable speaker references.
4. Answer quality: serialize untrusted evidence, apply a deterministic grounding
   guard, expose provenance, and add a memoir evaluation runner and sample cases.
5. Voice and UI: cancellation, reference revocation, model revision configuration,
   synthesis metrics, retry controls, audio access, and browser regression tests.
6. CI: pin action revisions and document scoped embedded-Chroma audit exceptions.

## Release review still required

- The deterministic grounding guard can reject valid paraphrases and does not
  establish semantic factual correctness. Evaluate it on reviewed real memories.
- Verify the Chroma advisory exceptions against current advisories before release.
- Exercise durable writes and recovery on the existing ExFAT deployment; passing
  isolated tests does not establish filesystem crash safety.
- Validate voice quality and interruption handling with actual local synthesis.
- Validate recording recovery on a physical iPhone, including backgrounding Safari.
- The evaluation sample contains placeholder IDs and is not a completed quality benchmark.
- Review the complete diff before merging; the changes span multiple workflows.

## Repository hygiene

Validation after blocker remediation on 2026-10-26: a fresh Docker test build
passed 140 backend tests; Ruff and dependency consistency checks passed. The full
WebKit suite passed 27 checks (16 mobile, 11 desktop); five phone-only checks
were intentionally skipped on desktop. JavaScript syntax and `git diff --check`
passed. The append-only scan found no Chroma deletion calls. These checks use
isolated test data and mock voice synthesis/media where appropriate.
They do not replace the release review above or a complete security audit.

The operational checkout's untracked `.claude/` folder contains local tool
configuration and is intentionally excluded from this application checkpoint.
Runtime data, recordings, models, credentials, and generated test artifacts must
remain outside commits. Preserve the production branch until this candidate is
reviewed and deliberately promoted.

## New local-first improvement sequence (authorized 2026-10-26)

This is a separate eight-stage program, not a claim that the earlier Phase 1–5
checkpoint already implements the performance recommendations.

1. Baseline: reconcile source hashes; approve audio sample selection; review
   expected memoir facts; collect separate retrieval/load/generation/voice times.
   Inventory and timing tools are available. Gold answers remain provisional.
2. Storage/recording: bounded transient retries, source checksum verification,
   recoverable browser drafts, interrupted-source retention, restore tests.
   Initial implementation is in the candidate; physical-device and ExFAT acceptance,
   resumable/idempotent uploads, and active-recording crash coverage remain.
3. Local resource coordination: use the baseline to select short embedding
   residency, explicit context budgets, heavyweight admission control, idle unload.
4. Retrieval: memoir-first routing and evaluated lexical/passage/threshold changes;
   embedding formatting changes require a separate versioned index and rollback.
5. Native transcription: compare MLX Whisper, Parakeet, and other justified
   candidates on identical approved audio with corrected reference transcripts.
6. Voice clone: compare batch sizes and precision; preserve complete-WAV playback,
   reusable conditioning, immediately durable segments, cancellation.
7. Optional local speaker processing: diarization and recognition with mandatory
   human confirmation of identities and subject/interviewer roles.
8. Answer models: compare Gemma and alternatives only after stages 3–4 stabilize.

No storage migration, Chroma deletion, automatic index activation, model switch,
or production deployment is part of these candidate edits. Complete stages in
order and record actual measurements before selecting replacements.

Initial embedding experiment (2026-10-26, 16 GiB Apple Silicon Mac): three
unload-after-query wall times were 0.681/0.666/0.666 seconds; a short-residency
series was 0.667/0.115/0.115 seconds. This used one synthetic query, no library
writes, and no concurrent test run. It measures model residency, not disk-cache
cold start or full answer latency. The tested embedding model was unloaded
afterward. Do not generalize this to voice synthesis speed.

The new work is isolated on `codex/local-first-baseline`, stacked on the earlier
Phase 1–5 candidate. Neither candidate has been deployed. Read-only runtime
reconciliation matched all 23 scoped active source files to the operational
checkout at `3cc3869`; the dormant `app/app/` prototype is excluded. The two
approved originals were hash-verified unchanged. Private case files remain
ignored by Git and excluded from Docker build context.

The first increment adds source/timing inventory, a reviewed-case gate,
checksum-verified uploads, bounded filesystem retries, and browser recovery
copies for finalized recordings. Incomplete browser drafts remain retained but
are not presented as safe to upload. Browser recovery is origin/profile-specific
and does not establish physical iPhone, background-recording, or crash safety.
No real-corpus quality score, native transcription comparison, voice-speed
comparison, or completion of stages 3–8 is claimed here.

Initial-increment validation: 150 backend tests passed; Ruff and dependency
consistency checks passed. The complete WebKit suite passed 35 checks, with five
phone-only checks intentionally skipped on desktop. It covers failed-upload
reload/retry, missing-chunk rejection, unavailable draft storage, and stale
recovery lookups. JavaScript syntax and whitespace checks passed. These tests
use isolated data and synthetic media, not the physical phone or production
Chroma. Deprecation warnings from upstream test dependencies remain.

## Workload candidate and external-drive evidence (2026-10-26)

Branch `codex/local-workload-coordination` adds heavyweight admission control,
finite embedding/language residency, explicit context budgets, released Whisper
instances, native voice model-only unloading, bounded stream-cancellation watcher
lifetime, and accurate voice-busy messages. It also verifies atomic writes by
reading them back and rejects unsafe/unverified backup paths. This is candidate
work, not a deployment or evidence that all eight stages are complete.

The existing Personal volume was confirmed as ExFAT without changing it. Tests
used only `/Volumes/Personal/here-i-am-validation.aXczUx`, containing synthetic
files and newly created databases. Production recordings and Chroma were not
opened for writes. Diagnostic artifacts were retained.

| Check | Native macOS on Personal | Docker bind mount of Personal |
| --- | --- | --- |
| Immediate read after fsync + atomic rename | 10/10 succeeded, repeated twice | 0/10 immediate; all readable after one 100-ms retry, repeated twice |
| Second process excluded by flock | Yes | No |
| Simple SQLite WAL, ten inserted rows | Passed | Passed |
| Full scratch Chroma backup/restore exercise | Not run natively | Failed during fresh Chroma initialization: SQLite reported a readonly database |

The first broad external exercise had six failures and ten passes, including
unretried reads, the new Chroma initialization, and ineffective locks. After
read-back verification and keeping coordination files inside the container, a
focused run passed 13 checks. Session-state/revision fixtures were on Personal;
pytest temporary corruption/lock fixtures were on container-local `/tmp`. This
is not a passing full external Chroma restore, power-loss test, or iPhone test.

Do not mark the external-storage acceptance gate complete. The evidence points
to problems at the Docker bind-mount boundary but does not establish a single
root cause for Chroma, nor prove native Chroma reliable. A useful next experiment
is a native-backend/Chroma restore in an isolated copied library on the same
ExFAT volume, preserving original locations and requiring no APFS conversion.
Obtain direction before changing the production execution/deployment architecture.

Final candidate validation: 166 backend checks passed (14 upstream deprecation
warnings); Ruff, dependency consistency, JavaScript/shell syntax, and whitespace
checks passed. The complete isolated WebKit run passed 37 checks, with five
phone-only checks intentionally skipped on desktop. The browser harness now
disables access to real inference endpoints, so synthetic browser tests cannot
warm or cancel the user's native models. These results do not supersede the
failed external Chroma acceptance gate. Native GPU memory release, physical
iPhone behavior, real-corpus answer quality, and end-to-end latency have not been
validated for this increment. Production source reconciliation still matched all
23 scoped active files at operational commit `3cc3869`; nothing was deployed.

### Native synthetic storage pilot (2026-10-26)

The follow-up pilot used a separate temporary native Python environment, not
the installed application/voice environments. It ran the candidate's existing
tests with `TMPDIR` pointing to the synthetic external-drive validation folder.
No production library was copied or opened by this pilot. Inference endpoints
were disabled by the test harness; no models or real recordings were processed.

- Native storage, restore-safety, cross-process coordination, and full synthetic
  Chroma backup/restore: **18 passed**, 13 upstream Pydantic deprecation warnings,
  7.56 seconds.
- A second full synthetic backup/restore in a fresh database: **1 passed**,
  13 warnings, 1.82 seconds.
- A new Python process reopened the first restored collection and retrieved the
  retained archived synthetic document by explicit vector query, with count 1
  and distance 0.0. Original synthetic source count/content remained intact in
  the backup test. No collection/record deletion was performed.
- Dependency consistency check passed. Chroma logged a PostHog API-signature
  mismatch despite telemetry being disabled; it did not prevent the query.

Runtime: macOS 27.0.1 arm64, Python 3.11.14, Chroma 0.5.23,
chroma-hnswlib 0.7.6, NumPy 2.4.6, Pydantic 2.11.3, PostHog 7.75.11.
Top-level dependencies used the repository pins; transitive dependencies are
not fully locked, so this is not a platform-only controlled comparison with
Docker. Resolve/pin a tested dependency set before a production native rollout.

Retained synthetic restored roots are under
`/Volumes/Personal/here-i-am-validation.aXczUx/`:
`here-i-am-empty-restore-obvq1dsq` and `here-i-am-empty-restore-iqtv2prw`.
The isolated runtime is `/private/tmp/here-i-am-native-pilot-20261026` and is
temporary, not a production installation.

This clears the *native synthetic restore* check, not the Docker storage gate
or production acceptance. Next: create/verify a consistent application-level
backup, restore it into a separate native pilot data root on the same ExFAT
volume, compare all collection counts and representative retrieval results,
then exercise the pilot server on a separate loopback port. Never copy a live
SQLite database as the backup method. Keep all original Chroma records and the
current deployment intact; do not convert the filesystem. Physical iPhone,
concurrent operations, failure recovery, and real-library performance still
require acceptance testing before any deliberate cutover.

### Real-library native preservation pilot (2026-10-27)

Production stayed online and unchanged. No background jobs were active at
preflight. The deployed older backup exporter handles only the default Chroma
collection, so this pilot instead made an isolated preservation snapshot using
a read-only SQLite connection and SQLite's online backup API. It did not raw-copy
the live SQLite database. Source file inventories/checksums and SQLite
`data_version` were checked across copying; a change would reject the snapshot.
Chroma itself was opened only on the isolated copies, never on original data.

The snapshot copied and verified 573 files (727,937,969 bytes), including library,
speaker/profile, voice assets, and Chroma index files. Runtime logs/jobs/locks,
temporary files, model caches, exports, existing backups, auth tokens, and the
generation audit were excluded. This is a pilot preservation snapshot, not a
complete disaster-recovery backup. It is on the same drive as the originals.

The candidate's all-collection logical exporter then produced a verified backup
from that isolated snapshot. Restore into a new, empty native data root passed:

- 569 restored non-vector-export files matched the backup's size and SHA-256.
- All 208 records in `here_i_am_chunks` matched exactly across IDs, documents,
  metadata, and floating-point embeddings. Collection metadata also matched.
- Six stored-vector probes from the two approved sample sessions returned
  identical neighbor IDs and distances before/after restore.
- The restored library contained 72 session folders and no archived folders.
- Four user-confirmed retrieval cases each found the expected recording in both
  runs. The source was ranked first for three cases and second for one. This is
  a tiny retrieval set, not an answer-quality or hallucination benchmark.
- First retrieval took 2.204 seconds, including 1.960 seconds of embedding-model
  load time. Subsequent lookups took 0.128–0.271 seconds. The second-run median
  was approximately 0.144 seconds. No LLM answers or cloned speech were generated.
  This is not a controlled production-Docker/native speed comparison.

Following the verification skill's UI→API→data→render check, a temporary
read-only native server on `127.0.0.1:8792` served the real restored library.
Automated WebKit verified home and session API HTTP 200, the Memories view,
and a displayed count of 72; there were no page errors or unexpected HTTP
failures. An explicit pilot guard rejected writes with HTTP 403. Inference was
disabled for this browser check, and the pilot was not exposed through Tailscale.
This was not a physical Safari/iPhone, microphone, or playback test.

The pilot server was stopped afterward; port 8792 was closed. Production health
remained OK on port 8787. Ollama had no loaded models before the retrieval test
and was returned to that state afterward. No Chroma deletion calls were used.
Final source verification again matched all 573 original files to the pre-copy
checksums; pilot processing did not alter those files.
The unrelated Chroma/PostHog telemetry signature warnings remain a dependency
compatibility item; no memoir text was sent to any cloud inference provider.

Private evidence and retained copies live at
`/Volumes/Personal/here-i-am-validation.aXczUx/real-pilot-20261027/`:
`snapshot-verification.json`, `logical-backup-result.json`,
`restore-verification.json`, `retrieval-pilot.json`, `ui-verification.json`,
`snapshot/`, and `restored/`. Private memoir content is not committed to Git.

Recommendation: proceed toward a native-backend option, but do not cut over yet.
Next acceptance work is a reproducible locked native runtime and launcher,
path/secret isolation and production authentication, write/upload/recovery tests
on the copied library, voice-bridge integration, physical iPhone playback and
recording, then a reversible cutover/rollback rehearsal. Preserve current
storage locations and all Chroma records. Retrieval improvements, ASR/voice
benchmarks, speaker processing, and answer-model evaluation remain separate
roadmap work; this pilot does not complete those stages.

### Native launcher and authenticated write acceptance (2026-10-27)

Added `scripts/native_pilot.py`, a separate opt-in foreground launcher. It never
replaces the production/desktop launcher. It validates a path-bound pilot marker,
rejects known production roots/ancestors and symlink escapes, requires a separate
0700 state directory and 0600 independent passphrase hash, strips inherited
environment settings, and constructs explicit copied-library paths. It listens
only on loopback port 8792 by default. Cloud/voice/Ollama services are disabled;
only authentication, activity, upload and recording-validation-retry mutations
are permitted. Missing or invalid authentication at runtime returns HTTP 503,
rather than falling back to the app's unconfigured development authentication.

The 120-distribution native version lock was successfully installed into a fresh
Python 3.11.14 arm64 environment with `--no-deps`; `pip check` passed. Startup
checks versions against this lock. This reproduces package versions, not binary
artifact hashes or system FFmpeg builds; those remain release work. FFmpeg and
ffprobe 8.0.1 were used. Chroma/PostHog and upstream deprecation warnings remain.

The first acceptance run passed upload, draft recovery, and fail-closed auth,
then caught an immediate-restart problem in the launcher's port probe: TCP
TIME_WAIT was mistaken for an active listener. The probe now uses SO_REUSEADDR
like uvicorn; a regression test still verifies rejection of a real listener.
The first test copy and synthetic recordings were retained. A fresh restore
was used for the second run, which passed the complete sequence:

- Unauthenticated reads and wrong-password login: 401; correct login: 200.
- Cross-origin changes and disabled pilot operations: 403.
- Real native upload of a synthetic WAV: source bytes/checksum preserved,
  FFmpeg produced FLAC, recording entered the pending queue.
- Simulated validation interruption on that new fixture: retry rebuilt FLAC
  from the retained source and returned ready. No real recording was edited.
- Automated WebKit: login dialog→Talk; failed upload→IndexedDB recovery after
  reload→real successful upload; browser draft removed only after acknowledgement.
  No page errors. This is simulated capture, not a physical microphone test.
- Temporarily missing pilot passphrase file: 503; restored private hash resumes
  normal operation. Restart preserved authentication and both synthetic recordings.
- Logout revoked the session; subsequent protected access returned 401.

Final checks: **180 backend tests passed**, 14 upstream deprecation warnings;
Ruff, JavaScript syntax, and whitespace checks passed. Both original and pilot
Chroma still contained 208 vector rows. All 573 original files matched the earlier
snapshot checksums. Production health remained OK; the temporary server stopped
and port 8792 was closed. No source audio or Chroma records were deleted.

Private evidence is in ignored `reports/private/native-pilot-20261027-second/`
(acceptance report/server log/test credentials). The accepted copied library is
`/Volumes/Personal/here-i-am-validation.aXczUx/real-pilot-20261027/launcher-acceptance2/`.
It includes two retained synthetic test recordings in addition to the 72 real
session copies. The test passphrase was random and not logged; do not treat this
automated instance as a human-operated deployment.

Next gate: isolated cloned-voice integration and physical iPhone recording/playback,
then production service management, full backup/rollback rehearsal and deliberate
cutover approval. The current launcher intentionally blocks inference and VPN
exposure; it is not a production-ready replacement or a claim of completed
voice, latency, or all eight roadmap stages.

### Isolated cloned voice and private phone pilot (2026-10-27)

The next acceptance used a fresh restore (`voice-acceptance`) with 72 session
copies and 208 vectors, independent credentials/cache, native backend port 8792
and a separate authenticated MLX bridge on 8793. It reused the installed MLX
runtime and exact locally cached Qwen3-TTS 0.6B BF16 snapshot offline. No cloud
voice or answer service was used. Original references were not edited.

Measured results for one short fixture (not a representative benchmark):

| Check | Observed result |
|---|---|
| Complete WAV | 10.005 seconds of non-silent audio |
| First full request | 30.215 seconds |
| Bridge synthesis | 26.962 seconds, 2 segments, RTF 2.695 |
| Identical repeat | 0.054 seconds; identical WAV bytes |
| Active request cancellation | Released in 3.561 seconds |
| Model controls | Active unload refused; idle unload succeeded |
| Desktop WebKit playback | One click, nonzero audio signal, completion, answer retained |
| Reference preservation | Both copied reference files unchanged |

This is successful functional integration, not proof that long-answer synthesis
is fast enough or that voice fidelity is acceptable. BF16/4-bit comparison,
larger samples, and physical-speaker confirmation remain open. The installed
MLX/Transformers model-architecture warning did not prevent the fixture from
completing but remains a compatibility observation.

The user then approved a separate physical iPhone pilot. A private Tailscale
HTTPS route on 8443 now points only to the pilot; the normal 443→8787 route was
verified unchanged. The pilot has a rotated independent passphrase, separate
host-scoped cookie name, exact trusted origin, copied data, and no cloud keys.
Talk inference, embedding, voice enrollment/revocation and destructive changes
remain disabled. A clearly labeled “Load voice test” control loads the complete
accepted sample into the real playback controls. Remember uploads remain enabled
only against the isolated copy. The supervisor is left running for the user test.

Automated mobile WebKit through the real HTTPS route passed login, preservation
of a sentinel production cookie, unauthorized-audio rejection, disabled inference
and embedding, Ready—Play with one click, native HTML audio time advancement
(unmuted, volume 1), playback completion, retained answer on Talk, secure microphone
API availability, and navigation to Remember. No JavaScript errors were observed.
**Physical iPhone speaker output and microphone recording/save are not yet verified.**

Regression: 194 backend tests passed with 14 upstream deprecation warnings; Ruff
and JavaScript syntax passed. A preliminary test invocation omitted the repository's
documented `PYTHONPATH=app` and failed collection; the corrected invocation passed.
Final preservation checks found zero mismatches across 573 original files;
production and pilot both still had 208 vectors, and production health was OK.
Private voice/phone evidence and the sample are in ignored
`reports/private/native-voice-20261027/`. No credentials or personal audio are
committed. No APFS change, production cutover, or Chroma deletion occurred.

### Physical iPhone acceptance and backup/rollback rehearsal (2026-10-27)

The user confirmed hearing the complete cloned-voice sample on the physical
iPhone, then reported one new recording waiting. The pilot logged a successful
upload. Its retained M4A source matched the stored SHA-256, and the derived FLAC
was valid mono 16 kHz audio lasting 14.036 seconds. It is safely queued with
`upload_status=ready`; transcription, analysis and embedding remain pending by
design. This clears physical playback and recording-upload acceptance, not
transcription accuracy or conversational voice-latency acceptance.

With authorization to proceed, only the known iPhone pilot supervisor was stopped.
Production Docker, the production voice bridge and port-443 route were untouched.
A full logical pilot backup was stored on the Mac's existing FileVault-encrypted
internal volume, and restore targeted a new folder on the existing ExFAT external
volume. This is a second-volume backup, not an APFS migration or off-site backup.

The rehearsal found and fixed a real cross-filesystem restore bug:
`shutil.copy2` attempted macOS `chflags` on ExFAT and failed with `EINVAL` after
copying the first file. Restore now copies portable permissions/timestamps only,
flushes and verifies each destination against the manifest. It does not blanket-
ignore filesystem errors. Regression tests cover unsupported flags, corrupted
destination bytes, and permission failures. The first backup and partial restore
were retained, and the second attempt used new destinations.

The second restore passed file/vector checks, then the harness incorrectly counted
73 AppleDouble sidecar files as additional sessions. Session counting now requires
real directories and excludes `._` sidecars, with a regression test. Only the
remaining restored-app check was resumed; the original failed-stage report is
retained for audit, rather than claiming a single uninterrupted successful run.

Combined acceptance evidence:

| Check | Result |
|---|---|
| Backup | 574 manifest files, 732,741,445 bytes; 2.85 seconds |
| Restore | 5.11 seconds for copy/rebuild; additional verification separate |
| Restored ordinary files | 573 checksum/size matches, including the iPhone recording |
| Private runtime recovery | 4 independently verified files; no credentials logged |
| Memory library | 73 sessions visible in restored WebKit UI |
| Chroma | 208 vectors; IDs, documents, metadata, embeddings and collection metadata identical |
| Retrieval | 8 stored-vector probes; identical IDs and distances |
| Overwrite guard | Restoring into the occupied target refused |
| Recording delivery | Authenticated audio checksum identical; browser loaded 14.036-second audio |
| Restored UI | Login, waiting status, memory dialog passed; no JavaScript errors |
| Rollback | Restored server stopped; original pilot restarted on the unchanged private route |
| Preservation | Original pilot credentials/session store and sample unchanged; 573 production source files unchanged |
| Production | Health OK; 208 vectors retained; production route unchanged |

The original iPhone pilot is available again with the same temporary passphrase.
The new recording remains in that pilot, not in production. The voice model is
unloaded while idle. No Chroma record or original recording was deleted.

Final backend regression: **204 passed**, 14 upstream deprecation warnings;
Ruff, JavaScript syntax and whitespace checks passed. Chroma/PostHog's existing
telemetry-signature warnings appeared with telemetry disabled and did not stop
the logical export or vector verification. Compatibility cleanup remains open.

Private evidence is under ignored `reports/private/restore-rehearsal-20261027/`
and `reports/private/restore-rehearsal-20261027-v2/`; the successful restored data
is `phone-backup-restored-20261027-v2` beneath the existing external-drive pilot
root. Backups and failed/complete restore copies are retained. Source code,
dependency artifacts, operating-system setup and downloaded models still need
a production recovery/packaging procedure. The next gate is native service
packaging and a reviewed production cutover/rollback plan, not automatic migration.

### Production cutover plan — not authorized or executed

The managed service work remains a candidate pilot. The pilot launcher still
rejects production paths and blocks Talk inference, embedding and maintenance.
Successful pilot recovery is not proof of production workflow compatibility.
Do not remove those guards just to make a production launcher.

Sequential gates before a deliberate switch:

1. **Package and supervise the candidate.** Use a durable independent runtime,
   artifact-pinned wheels and a read-only committed source release. Validate
   normal start/stop, duplicate-start refusal, child and supervisor crash recovery,
   data-volume absence, restored authentication and no orphan listeners. Keep
   production 443→8787 and the original desktop launcher unchanged. Pilot-only
   current-login operation can proceed; unattended login startup is a separate
   deployment decision.
2. **Complete the production-equivalent configuration on another copy.** Model
   local answer/embedding/voice and optional explicitly selected cloud answers as
   separate capabilities. Preserve no-automatic-fallback policy. Validate every
   storage/lock/credential path, token permissions, host/origin and local bridge
   identity. Add no cloud keys to source, profiles, logs or command arguments.
   Do not enable recording processing on the currently preserved pilot casually.
3. **Run full workflow acceptance.** Authenticated Safari/iPhone recording upload
   and draft recovery, queued local transcription/embedding, append-only vector
   versioning, four reviewed memoir retrieval cases, answer grounding/abstention,
   correct provider labeling, complete cloned WAV playback, cancellation/resume,
   and simultaneous-workload/memory behavior. Test the larger backlog and restart
   recovery. Current service/restore checks do not replace these tests.
4. **Rehearse old-to-new and new-to-old compatibility.** Test the actual deployed
   source revision, not just the candidate restarted against itself. Introduce
   synthetic post-cutover writes on a copy, then verify they remain recoverable
   when rolling back. Never roll back by overwriting newer recordings or deleting
   vectors. If the older app cannot read newer state, use a reviewed export/replay
   path or forward repair before permitting production writes.
5. **Freeze and protect production for the change window.** Obtain explicit
   approval and announce a brief pause. Drain active recordings/jobs and persist
   browser drafts. Make fresh encrypted, second-volume logical and runtime/source
   recovery artifacts; verify restore and all Chroma collections. Capture exact
   old image/source, ports, routes, credentials and service ownership. Stop only
   verified owned processes. Keep the current ExFAT storage layout; do not convert
   filesystems or run native and Docker writers concurrently on the same data.
6. **Switch with rollback boundaries.** Start the approved production-capable
   release only after its staged gates pass. Check loopback readiness, auth and
   data before changing the normal HTTPS route. A health endpoint alone is not
   success. Run agreed smoke tests. On failure, freeze new writes, preserve all
   post-switch data, and use the tested compatibility procedure. Do not point an
   old container at a database it has not been proven able to read.
7. **Observe, then retire nothing automatically.** Review activity/errors,
   pending jobs, recording integrity, vector counts and memory pressure. Keep old
   releases and backups until the user approves retention changes. No Chroma
   deletion, raw SQLite overwrite, APFS migration, or automatic provider change.

Remaining packaging limitations: the backend still depends on the installed
Homebrew Python/FFmpeg binaries; the voice runtime and model have not received a
fresh artifact-pinned rebuild; launchd current-login recovery is not login/reboot
validation; backup copies are not off-site. None should be implied complete by
passing the native pilot tests.
