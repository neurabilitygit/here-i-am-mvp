# Native production cutover — 2026-10-27

## Outcome

Production now runs the FastAPI/Chroma application, voice bridge and Ollama
control bridge natively under a supervised, current-login macOS service.
The immutable deployed release is `0c2e31a6e9a880858e3635f38fbef341c9df916c`
from `codex/local-workload-coordination`. Subsequent documentation commits do
not change the running source. The reviewed source is on GitHub in draft PR #7.

The normal local port remains 8787; local voice/control remain 8779/8778.
The existing private Tailscale HTTPS hostname and passphrase are unchanged.
The separate test service and port-8443 route were retired after preserving
the real phone recording. Pilot/staging data and their immutable releases remain.
Other Docker applications were not changed.

## Preserved data and preferences

- Data is still `/Volumes/Personal/here-i-am` on ExFAT. No APFS conversion or
  data-root relocation occurred.
- Every original Chroma ID, document, metadata value and embedding was compared
  against a stopped-production snapshot: **208 original records unchanged**.
  No collection activation, re-embedding, archive removal or deletion occurred.
- **378 original library files** were checksum-verified unchanged against the
  fresh production backup. Physical Chroma index headers and operational logs
  can change when a process opens the database; integrity was checked logically
  for those records, not by assuming every database byte must stay identical.
- The existing passphrase hash and preferences were checksum-verified unchanged.
  Safari's existing login worked after cutover. The local answer-engine choice,
  saved OpenAI model choice, protected API-key file, local voice consent and
  reference remain in use. No cloud generation was used for acceptance testing.
- The real 14.036-second phone recording was copied from the pilot, with all
  file hashes verified, into the main library. Its pilot original and separate
  safety copy remain. The main library has **73 recordings, one queued**.
  Synthetic staging recordings were not imported.

## Verification and measured results

These are single-machine acceptance observations, not universal performance claims.

| Check | Result |
| --- | --- |
| Native backend regression suite | 232 passed; 14 upstream deprecation warnings |
| Isolated WebKit suite | 37 passed; 5 intentional phone-only desktop skips |
| Ruff, dependency consistency, shell syntax, whitespace | Passed |
| Staging memory batch | Queued real-phone copy processed; 208 old vectors retained, 209 total |
| Schema-constrained metadata retry | 84.23 seconds; reused the already saved transcript |
| Reviewed local answers | Birthplace, early move, relocation year and school grade passed |
| Unsupported synthetic question | Returned the unknown-answer response |
| Live failed-upload/reload/retry | Draft recovered; real retry upload acknowledged; draft cleared only afterward |
| Short cloned-voice sample | 4.615 seconds of audio in 28.95 seconds; cached replay request 0.047 seconds |
| Production private HTTPS flow | Local answer 23.76 seconds; subsequent voice preparation 67.02 seconds |
| Production complete audio | 17.32-second WAV, one synthesis request, one Ready—Play tap, playback completed |
| Production answer/controls | Answer stayed visible throughout; clear control worked; both engine choices available |
| External Safari | Existing authenticated session opened the new build and retained settings |

The production flow used iPhone-style WebKit with a real native HTML audio
element; its media clock advanced, output was unmuted at volume 1, and playback
completed. This is **not a new physical iPhone speaker test**. The user had
previously confirmed hearing the separate pilot sample. Repeat a physical-device
check at the normal URL when convenient; do not claim it already happened.

Three issues found during migration were corrected before cutover:

1. Local metadata returned a null value where the data contract requires text
   or a list. The existing one-call generation now requests the validated JSON
   schema; malformed metadata is still rejected rather than fabricated.
2. Direct-evidence ranking missed ordinary verb inflections and buried a
   relevant date. It now ranks explicitly requested dates/grades among relevant
   subject evidence without an extra model call or changing stored vectors.
3. Service replacement could race asynchronous shutdown. Stop now waits for
   ownership and ports to clear; start rejects a different still-loaded release.

The recovery test originally navigated during initial banner requests, exposing
a WebKit navigation-abort error. It now waits for initialization before testing
the failed-upload reload boundary and reports actual JavaScript errors.

## Backup and recovery material

Private evidence root:

`/Users/ericbass/Library/Application Support/Here-I-Am/native-migration-20261027`

The fresh stopped-production full backup is:

`/Users/ericbass/Library/Application Support/Here-I-Am/native-production/backups/20261027T175403.863739Z`

It contains 1,357 manifest entries and 1,330,395,526 bytes, including a portable
export of every Chroma collection. It was restored to a new empty validation
directory on the same external ExFAT drive; every exported vector value matched.
The phone addition was imported after that snapshot and has its own verified
safety copy under the private rollback directory.

Rollback material also includes the stopped original container, its exported
image, raw stopped Chroma copy, prior Git bundle/configuration, protected secret
copies, and old desktop launcher. The old container's restart policy is now
`no` to prevent two independent writers. It was **not removed**.

The old Docker image can read the updated session/record data, but its library
enumeration fails on AppleDouble entries on the ExFAT bind mount. Therefore an
automatic return to that old container is **not approved**. Prefer repair of the
native release; if Docker rollback becomes necessary, first fix and validate
that enumeration problem on a copy, preserve all post-cutover additions, stop
all native writers, take a new backup, and verify the intended data root. Never
overwrite the live library with an older snapshot or delete Chroma records.

Git also encountered verified AppleDouble metadata masquerading as object/ref
files. These files were quarantined, not deleted; Git integrity then passed.
The external checkout's user-owned `.claude/` directory remains untouched.

## Operating the native deployment

- Double-click `start-here-i-am.command` or `Here I Am.app` on the desktop.
  The command now reads the protected production profile, starts Tailscale and
  the native service, and opens Safari. It no longer depends on Docker startup
  or retrieving Railway credentials on ordinary launches.
- `scripts/start.sh` forwards to the native launcher when the profile exists.
  It is idempotent for the active release. `scripts/status.sh` reports all five
  service/readiness checks. `scripts/stop.sh` stops only the owned native group;
  reused Ollama and Tailscale remain available to other applications.
- Native profile: `.../Here-I-Am/native-production/production.json` (mode 600).
  Service state and private logs: `.../Here-I-Am/native-production/state`.
  The supervisor restarts its owned group after repeated health failures or a
  child exit. It fails closed if authentication/storage is missing.
- Source releases are read-only hashed Git snapshots. Native dependencies are
  pinned and installed in the separate durable runtime; voice keeps its existing
  MLX environment and BF16 model. No model was silently changed.
- The service is loaded for this login, **not** installed as a new login item.
  Run the desktop launcher after a reboot. Keep the external drive mounted and
  the Mac awake for phone access.

## Remaining work, outside this runtime migration

The eight-stage performance program is not complete. Native MLX/Parakeet
transcription comparisons, local diarization, broader retrieval/model quality
evaluation, upload idempotency, and additional voice optimization remain separate
increments. The existing local voice is still slower than real time; moving the
backend out of Docker does not remove the Qwen synthesis workload.

Restore checks do not establish power-loss safety, and IndexedDB cannot guarantee
survival of Safari eviction or an un-emitted active recording. The safety copies
are local, not offsite disaster recovery. Upstream dependency warnings and the
documented embedded-Chroma advisory exceptions still need maintenance.
GitHub CI is additional evidence; local acceptance results above do not imply
that a still-running hosted workflow has completed.
