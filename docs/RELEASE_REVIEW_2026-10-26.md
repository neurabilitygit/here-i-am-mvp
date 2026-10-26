# Phase 1–5 release review

## Blocker remediation — 2026-10-26

The issues below have been patched on `codex/phase-1-5`; production remains
unchanged and this is not deployment approval.

- Grounding compares normalized numeric tokens and word-bounded entities,
  including names at sentence starts. Questions are no longer treated as
  evidence. Audits report `grounding_check_passed`, not semantic support.
- Personal/hybrid answers are buffered until the final deterministic check.
  This adds no model call, but delays visible text until generation completes.
- Voice revocation clears the model's conditioning cache, releases the model,
  and fails closed if cleanup fails. Lock release is guaranteed; cached playback
  and warmup also participate in the lifecycle lock.
- Backups fail on unreadable source files, verify copied checksums, export all
  Chroma collections and their metadata/counts, and validate isolated restores.
  Restore remains empty-target-only and supports legacy single-collection backups.
- iPhone preparation now hides Cancel when Ready. Canceled voice requests lose
  ownership immediately, so their late completion cannot clear a newer request.
- The native-media browser test now isolates its fake audio transport from the
  real decoder instead of allowing invalid fixture bytes to trigger media errors.

Regression checks include unsupported numbers/names, valid paraphrases, streamed
rejection, idle/active voice revocation, cleanup failure, unreadable backup files,
and multi-collection restore. Final check results are recorded in
`docs/PENDING_HARDENING_REVIEW.md`.

Remaining release gates: reviewed real-memory accuracy, real local voice listening,
physical iPhone recording/playback, and ExFAT recovery acceptance. A deterministic
heuristic does not establish semantic factual correctness. No APFS migration,
production-data rewrite, or Chroma deletion was performed.

## Original review evidence (before remediation)

Candidate: `d90a1b5`, compared with deployed baseline `3cc3869`.
Decision: keep as a draft; do not merge or deploy yet.

## Confirmed blockers

### P1: The new grounding guard approves unsupported facts

`app/services/pipeline.py:1678-1686` uses substring membership for numbers and
skips every capitalized entity at the beginning of a sentence. Executing the
actual function extracted from the source with synthetic fixtures produced:

| Recorded evidence | Generated answer | Actual guard result |
| --- | --- | --- |
| I was 10 years old. | I was 1 year old. | supported=True |
| I grew up in New York. | Boston was where I grew up. | supported=True |

The question was "Tell me about childhood." in both cases. This is a regression
in the promised validation behavior, not proof that the previous prompt-only
version was factually safe. Match complete normalized numeric tokens, handle
sentence-initial proper names, and distinguish "no heuristic violation found"
from semantic support. Add adversarial and valid-paraphrase regression cases.
Do not represent this heuristic as proof of answer accuracy.

### P1: Voice revocation does not release all cached conditioning

`scripts/mlx_voice_bridge.py:439-448` clears the bridge waveform variables and
derived audio files but retains `_model`. The installed MLX Qwen implementation
has `_icl_cache`, storing reference audio codes and reference text tokens.
Revoking the reference therefore leaves derived voice identity in process memory.
Release the model or explicitly clear its reference caches while holding the
generation lifecycle lock. Verify revocation both when idle and during a job;
also ensure a cleanup failure cannot permanently strand the generation lock.
No live reference was revoked during this review.

## Additional release concerns inherited from the baseline

- Backup enumeration in `app/services/library.py:383-394` suppresses arbitrary
  `OSError` values when testing files. An inaccessible authoritative file can be
  absent from a backup that is later presented as complete. Explicitly skip
  known sidecars, but fail or mark the backup incomplete for other read errors.
- The backup exports only the active Chroma collection and excludes the physical
  Chroma directory. Preserve and verify every collection needed for recovery,
  including migration collections, without deleting records.
- Streaming sends raw tokens before applying the final guard. Replacing the
  answer afterward does not prevent the user from seeing unsupported text.
  Decide whether provisional text is acceptable, and test the final answer/TTS
  transition on a physical iPhone.

## Verification and boundaries

The preceding checkpoint passed 129 backend tests, nine selected mobile Safari
tests, Ruff, and whitespace checks. This review additionally reproduced the
grounding failures directly from the candidate function without importing the
application or touching its database.

Production files and the deployed container were not changed. ExFAT remains a
requirement. No Chroma data was deleted or rewritten. No real-memory quality
benchmark, voice-clone listening test, or physical-iPhone recovery test was
completed by this review.

## Next implementation order

1. Correct the grounding guard and its audit terminology; add regression cases.
2. Complete voice-cache revocation and failure-safe lock release.
3. Make backup completeness explicit and verify isolated restore coverage.
4. Finish security/CI review and physical-device acceptance.
5. Promote only after the above checks pass; retain the production baseline as
   the rollback target.
