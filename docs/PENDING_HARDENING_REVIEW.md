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
