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
