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
