# Non-destructive refactor migration

The production runtime was moved from Docker to native macOS on 2026-10-27;
see [the cutover record](NATIVE_MIGRATION_2026-10-27.md). Storage stayed on the
existing external drive and the active vector collection was not changed.
The earlier implementation notes below describe the original refactor.

## Implemented phases 1-6

1. Characterization: isolated test target and API/storage/pipeline/job/library tests.
2. Consolidation: root build explicitly uses the single `app/` implementation; dormant alternatives are documented as legacy.
3. Durable state: atomic writes, locks, persistent serialized jobs, transcript revision history, reconciliation, archive/export/backup contracts.
4. Vector evolution: semantic word-bounded chunks, versioned metadata, deterministic IDs, and a separate migration collection.
5. AI quality: full-input staged metadata processing, validated structured output, explicit routing, configurable temperature/distance, source evidence, and prompt-injection boundary tags.
6. Product/security: session library, transcript review, job history, source display, backup/export UX, upload limits, localhost binding, restricted hosts/CORS, and security headers.

## Compatibility

Existing session folders and `here_i_am_chunks` remain readable. No startup migration runs. Missing v2 state is handled conservatively. Existing artifacts are not rewritten merely by opening the application.

## Future cutover procedure

1. Back up the data volume and run reconciliation.
2. Deploy the refactored application without changing `CHROMA_COLLECTION`.
3. Explicitly start the side-by-side reindex and inspect job totals/errors.
4. Compare representative retrieval results between collections.
5. In a later approved change, switch the environment to `here_i_am_chunks_v2`.
6. Retain the original collection permanently. Never delete Chroma records.

No migration or deployment against personal data was performed during implementation.
