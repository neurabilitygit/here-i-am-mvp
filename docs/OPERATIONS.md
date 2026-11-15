# Operations

## Startup checks

1. Confirm `/Volumes/Personal/here-i-am` is mounted.
2. Confirm the private native profile exists at `/Users/ericbass/Library/Application Support/Here-I-Am/native-production/production.json`.
3. Run `scripts/start.sh` or the desktop launcher. With that profile present, it verifies the immutable release/runtime/storage, starts or reconnects Tailscale, starts the managed native app/voice/control service group, and publishes its authenticated loopback listener to the private tailnet. It reuses a running Ollama server or starts one if needed. Docker is not required.
4. Check `/api/health` for application/storage liveness and `/api/ready` for Ollama readiness.
5. Check `http://127.0.0.1:8779/health` and `http://127.0.0.1:8778/status`, or run `scripts/status.sh`. Use `scripts/stop.sh` to stop the managed app and its owned children. A reused shared Ollama server and Tailscale are not stopped.

The production service is managed for the current login, not installed as a new
login item. Run the desktop launcher after restarting the Mac. The production
profile references source release `0c2e31a6e9a880858e3635f38fbef341c9df916c`;
editing a checkout does not update this release. Stop and verify the old service
has exited before activating another reviewed profile. See
[the cutover and recovery record](NATIVE_MIGRATION_2026-10-27.md).

The existing Railway-sourced OpenAI credential is retained in the protected
mode-600 host secret. Native production reads that file directly; the launcher
does not fetch cloud secrets on ordinary restarts. Secret values are never
placed in the profile, preferences, logs, or source control. The user's existing
Local Gemma selection and saved OpenAI model preference were preserved.

## Remote access via Tailscale

Here I Am can be reached from a phone without exposing any port to the LAN or the public internet, using a private Tailscale mesh network plus a login gate:

1. Install Tailscale on this Mac and on the phone, and sign both into the same tailnet once.
2. Set the shared login passphrase once: `./scripts/set_passphrase.py`. This writes a PBKDF2 hash (never the plaintext) to a mode-600 file under the same secret directory as `local_bridge_token`; `scripts/start.sh` refuses to start without it.
3. Run `./scripts/start.sh` as usual. The launcher opens Tailscale if needed and reconnects without changing the device's existing tailnet preferences. The native profile retains the approved HTTPS origin and trusted host. The application binds to `127.0.0.1:8787`; Tailscale Serve forwards the normal private HTTPS address to it. The separate port-8443 pilot route has been retired.
4. Open the HTTPS URL printed by the launcher on the iPhone while its Tailscale connection is active, then log in with the passphrase from step 2. The session cookie is `HttpOnly`, `Secure`, and expires after `AUTH_TOKEN_TTL_SECONDS` (default 30 days).

For deliberate local-only maintenance, run `HERE_I_AM_ENABLE_TAILSCALE=false ./scripts/start.sh`. Any other value fails closed. `./scripts/enable_tailscale.sh` remains available as a standalone repair command and now starts or reconnects Tailscale itself.

Every route except `/`, `/static/*`, `/api/health`, and the login/status/logout endpoints requires a valid session cookie — enforced centrally in `request_observability` in `app/main.py`, so new routes are protected by default. Repeated wrong passphrases lock out further attempts for `AUTH_LOCKOUT_SECONDS` (default 15 minutes).

## Production answer-engine controls

The production UI exposes two explicit choices under **Settings → Talk answer engine**:

- **Best answer — OpenAI GPT** uses the configured `OPENAI_MODEL` only for final Talk composition.
- **Private answer — Local Gemma** uses `OLLAMA_CHAT_MODEL` and keeps generation on this Mac.

The selected provider is persisted atomically in `/data/appdata/preferences.json`. A change is rejected before persistence when the destination provider is not usable: Local Gemma requires a reachable Ollama service and an installed chat model; OpenAI requires a production credential and a model in `ALLOWED_OPENAI_MODELS`. There is no automatic fallback in either direction. The settings response and `/api/providers/status` never expose credentials.

Production defaults disable browser entry of API keys with `ALLOW_RUNTIME_CLOUD_KEY=false`. Prefer a mode-600 host secret mounted read-only and set `OPENAI_API_KEY_FILE` to its container path. Browser-entered session keys are intended only for controlled development and require `ALLOW_RUNTIME_CLOUD_KEY=true`.

`/api/health` is the container liveness check. `/api/ready` is the deployment readiness gate and requires:

1. the data volume;
2. Ollama and the local `embeddinggemma` model, regardless of answer provider;
3. the currently selected answer provider.

Long local generations emit a server-sent-event heartbeat every 15 seconds. Upstream errors are logged locally while the browser receives a safe, actionable message without response bodies, credentials, or provider internals.

## Non-destructive controls

- Transcript updates create a prior revision and make derived analysis stale.
- Session archive requires `confirm=true` and moves, rather than deletes, data.
- Vector reindex requires `confirm=true`, writes only the migration collection, and does not activate it.
- Full rebuildable backups include original recordings, transcripts, revisions, versioned artifacts, preferences, audit/job/voice state, and a JSONL export of every Chroma document, metadata record, and embedding. Model weights are excluded. Set `BACKUP_ROOT` to another encrypted volume; the UI warns when backup and source share one device.
- Voice preparation requires explicit rights confirmation and creates only `appdata/voice/voice_reference.wav` plus its short reference transcript and consent status.
- Voice revocation disables synthesis and may delete derived references without touching session audio.
- Cloud generation never activates as an automatic fallback.
- Selecting OpenAI changes only Talk response generation. Retrieval still uses the existing local `embeddinggemma` index, and TTS still uses the local voice bridge.
- New recordings remain in the memory queue until the user explicitly confirms **Prepare all memories**. The warning states that Here I Am is unavailable for the duration. The batch runs serially, uses local `gemma4:e4b` for metadata and local `embeddinggemma` for vectors, and unloads both when complete. `/api/memory-batch/status` reports the queue, active job, models, and the hard-coded `openai_embedding_enabled: false` boundary.
- Conversation recordings additionally require `SPEAKER_DIARIZATION_PROVIDER=openai`, `SPEAKER_DIARIZATION_MODEL=gpt-4o-transcribe-diarize`, and the same protected OpenAI credential. Their compact audio analysis copy is sent only for speaker-aware transcription. Unknown voices pause for user review; neither metadata generation nor embedding begins until one memory subject is confirmed.
- Speaker avatar generation uses `AVATAR_IMAGE_MODEL=gpt-image-2`. It requires a source photo and an explicit rights checkbox. The source photo and existing art reference are sent to OpenAI; uploaded finished avatars never require cloud processing.

## Performance profile

The current local Talk model is `gemma4:e4b` with Ollama thinking explicitly disabled for interactive generation. Without that setting, the model can spend the entire output budget on hidden reasoning and return no visible answer. Quality-oriented retrieval uses 12 vector candidates, lexical reranking, 4 seed chunks, and neighboring-chunk expansion up to 6 context chunks.

The Talk settings provide Local Gemma and OpenAI GPT choices, plus a side-by-side comparison action. The comparison reuses one retrieval result and one prompt for both providers. Measure complete-answer time and inspect answer text and cited memories; it intentionally does not benchmark embeddings or voice generation.

Local cloned voice uses the Apple-native MLX Qwen3-TTS runtime. Its sentence foundry creates natural 15–30-word units, sends groups of up to four through MLX shared-reference `batch_generate`, applies the library's per-sequence text-length limits under a bounded group ceiling, and stitches the results with short pauses into one complete WAV. Safari never plays partial chunks. The reference waveform and MLX reference encodings are reused, while a persistent cache keyed by answer, voice reference, model, and speed makes repeated playback immediate. A 110-second no-progress watchdog and 120-second per-attempt ceiling bound synthesis; completed segments survive the ceiling so a retry resumes instead of starting over. Request IDs support exact cancellation, and an abandoned HTTP request cancels its native job. The optional “Prepare voice while I read” setting starts rendering when the written answer arrives. The dog-and-ball scene remains active until the full WAV is ready.

Before local synthesis, the app unloads configured chat/analysis models only when resident, leaving `embeddinggemma` untouched; the next local Talk request reloads its model normally. The bridge rejects overlapping synthesis with HTTP 409. The candidate browser displays the actual busy reason and preserves the written answer, rather than mislabeling every conflict as another voice file. A controlled four-segment benchmark on this Mac produced 35.04 seconds of audio in 50.56 seconds with the BF16 model. The 4-bit model produced 38.56 seconds in 179.51 seconds, so BF16 remains the default because its wall-clock generation was about 3.55 times faster (and its elapsed time per generated audio second was about 3.23 times better).

## Recovery

### Isolated native storage pilot (candidate, not deployed)

For the isolated native storage pilot (not a production replacement), use
`scripts/native_pilot.py`. The production launcher and desktop script remain
unchanged. The pilot never starts Docker, Tailscale, Ollama, or voice bridges.
It requires a restored copy with a marker bound to its resolved path, a separate
private state directory, and its own passphrase. It refuses the known production
data path, descendants/ancestors, symlink escapes, mismatched markers, unsafe
authentication files, occupied ports, and an unvalidated runtime.

Native pilot setup, from the repository root:

```sh
# Python must be the tested macOS arm64 3.11.14 build.
python3.11 -m venv /private/tmp/here-i-am-native-pilot
/private/tmp/here-i-am-native-pilot/bin/pip install --no-deps -r requirements-native-macos-arm64-py311.lock
/private/tmp/here-i-am-native-pilot/bin/pip check
# Replace these two paths with a verified restored copy and a NEW private
# directory on the Mac. Never point DATA at the production library.
DATA='/absolute/path/to/isolated/restored-copy'
STATE='/absolute/path/to/new-private-pilot-state'
/private/tmp/here-i-am-native-pilot/bin/python scripts/native_pilot.py init --data-root "$DATA" --state-dir "$STATE" --confirm-isolated-copy
/private/tmp/here-i-am-native-pilot/bin/python scripts/native_pilot.py check --data-root "$DATA" --state-dir "$STATE"
/private/tmp/here-i-am-native-pilot/bin/python scripts/native_pilot.py run --data-root "$DATA" --state-dir "$STATE"
```

Open `http://127.0.0.1:8792` in Safari; stop with Ctrl-C. It binds only loopback,
ignores shell/cloud credentials and `.env`, and disables inference. The pilot
allows only login/logout, activity logging, recording upload, and recording
validation retry mutations. Other mutations are rejected. It is intentionally
not usable for Talk inference or embedding. Voice and iPhone access require
the explicit opt-ins below; both remain off by default.
Authentication fails closed if its private hash disappears while running.

The native lock pins 120 installed distribution versions, including test tools;
it does not pin wheel hashes or system libraries. The tested audio utilities are
Homebrew FFmpeg/ffprobe 8.0.1. The launcher verifies dependency versions and utility
presence, not the utility build hashes. Native distribution packaging, security
review, and artifact-hash pinning remain release work. Do not use a temporary
environment as an unattended production service.

`scripts/check_native_pilot.py --data-root "$DATA" --state-dir "$STATE"
--confirm-pilot-mutations` is an explicit acceptance runner for a fresh,
uninitialized pilot copy. It creates an unlogged random test passphrase, launches
its own server, uses Node/Playwright WebKit, adds two synthetic recordings, tests
recovery/restart, and stops its server. It retains recordings and private logs;
it never deletes Chroma. It is not a physical microphone/iPhone test. State and
credentials from this automated run are test-only; use a separately restored
copy and the interactive `init` command for a human-operated pilot. To reuse
an accepted copy for a device test, stop it and use `set-passphrase` to rotate
its independent password and revoke its old test sessions first.

#### Isolated cloned voice and iPhone acceptance

`scripts/check_native_voice.py` accepts a fresh restored copy plus
`--voice-python`, `--model-path`, and `--confirm-local-clone-test`. It reuses an
installed MLX runtime and downloaded model offline. It starts a private-token
bridge on loopback 8793, then opts the pilot into that bridge with
`--enable-local-voice`. It checks complete-WAV output, identical cached output,
one-click desktop WebKit playback, cancellation, and idle model unloading.
It saves a short `local-clone-test.wav` in the private state directory and
stops its children afterward. It does not alter production voice references.

For a separately approved physical phone test, `scripts/run_native_phone_pilot.py`
supervises these same two services against the accepted copy. Required arguments
are `--data-root`, `--state-dir`, `--voice-python`, `--model-path`, and
`--pilot-origin https://YOUR-MAC.YOUR-TAILNET.ts.net:8443`. Use `daemonize.py`
with private PID/log files if the manual test must outlive the terminal. Stop
the recorded supervisor PID only after verifying it is this pilot; it then
terminates only its own two child processes. Never terminate production bridges.

The origin must be HTTPS on a `.ts.net` hostname at port 8443. The application
still binds only loopback, and uses a distinct `here_i_am_pilot_session` cookie
so logging into the test cannot overwrite the production login on port 443.
VPN routing is deliberately a separate operator action:

```sh
# Inspect first. Do not replace an occupied route or reset existing routes.
tailscale serve status --json
tailscale serve --bg --https=8443 http://127.0.0.1:8792
# After the physical test, remove only this added route:
tailscale serve --https=8443 off
```

Do not use Funnel. Confirm the production 443→8787 route is identical afterward.
The opted-in pilot adds a clearly labeled test-copy panel and authenticated
sample-audio endpoint. “Load voice test” loads the accepted complete WAV into
the real app playback controls; “Ready—Play” then exercises the normal iOS audio
path without another generation delay. This does not test generation speed on
the phone. Questions and memory processing remain disabled; Remember can record
and save only to the copied test library. All copies and Chroma records remain.

`scripts/check_native_phone_browser.cjs` reads its URL/passphrase on stdin and
checks mobile WebKit login, cookie isolation, authenticated audio, native-audio
time advancement, complete playback, retained answer, and the Remember screen.
Emulation is not physical iPhone speaker or microphone confirmation. The user
must hear the sample and make/save a short recording on their actual device.

#### Backup, restore, and rollback rehearsal

`scripts/rehearse_native_backup.py` accepts only a marked pilot with independent
private state, new backup/report and restore destinations, and an explicitly
selected validated recording. Stop the known pilot supervisor first; the runner
requires pilot ports 8792/8793 and restored-test port 8794 to be free. It never
stops services itself or changes Tailscale routes. Use
`--confirm-isolated-rehearsal` to acknowledge the copied-library writes.

Required arguments: `--data-root`, `--state-dir`, `--restore-root`,
`--report-dir`, and `--recording-id`. The report directory must be private and
outside both source and restored data roots. Prefer a different encrypted volume
for backup storage; no filesystem conversion is required. The runner:

- Creates the full logical data backup, including every Chroma collection.
- Saves an independent private recovery supplement for the pilot passphrase
  hash, session-token store, bridge token, and accepted voice sample. Keep this
  supplement encrypted and private; never commit it. Source/model packages and
  operating-system tools are not included in the data backup.
- Restores only into a new empty target, verifies every restored file, all vector
  fields and collection metadata, and compares stored-vector retrieval probes.
- Checks that a repeat restore refuses the now-occupied target without overwriting.
- Starts only the restored app on loopback 8794 with fresh test authentication.
  WebKit checks the library, pending recording, and playable audio metadata; the
  authenticated audio response must match the original file checksum.
- Stops its restored test server, retaining all data, backups and evidence.

The operator then restarts the original pilot supervisor and verifies its
credentials/session store, sample, saved recording, private route, and production
health. This is a pilot rollback rehearsal, not a production cutover. Failed or
interrupted restore folders are retained and must not be reused: choose another
new destination. Do not delete Chroma records as part of rollback.

Restore copies file contents, permissions and timestamps and verifies destination
checksums after flushing each file. It intentionally does not copy macOS-specific
Finder flags or extended attributes; those are outside the logical manifest and
can fail with `EINVAL` when restoring from the Mac to ExFAT. Permission, disk-full,
copy and integrity errors are still raised, not silently ignored.

#### Managed native pilot (current login only)

`scripts/native_service.py` packages a clean committed source snapshot and manages
only the fixed `org.hereiam.native-pilot` user service. It does not install a login
item, move data, change VPN routes, start Docker/Ollama, or switch production.
The service definition stays in its private bundle directory, not LaunchAgents.
`launchctl bootstrap gui/<uid>` loads it for the current login; `bootout` stops it.
This follows [Apple's launchd service-management model](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).

Prepare a durable Python 3.11.14 arm64 virtual environment separately from the
existing production and voice runtimes. `requirements-native-macos-arm64-py311.hashes.lock`
pins the 120 selected wheel artifacts by SHA-256. Download the matching wheelhouse
once, then install with `--no-index --find-links <wheelhouse> --no-deps --require-hashes`
and run `pip check`. These wheel hashes do not pin Python, macOS, FFmpeg, the
separate MLX voice runtime, or model weights; retain/version those separately.

Use `prepare --profile <new-private-profile.json>` with `--bundle-root`,
`--data-root`, `--state-dir`, `--backend-python`, `--voice-python`, `--model-path`
and the exact `--pilot-origin` on port 8443. Data/state must already pass pilot
validation. The bundle must be outside production, data/state and the checkout.
Preparation refuses a dirty checkout, existing profile/definition, source links,
unverified source contents, a temporary backend runtime, or dependency mismatch.
It archives the Git commit, adds a complete file-hash manifest, and makes the
release tree read-only. It does not copy untracked recordings, credentials or `.env`.

After stopping the known old pilot supervisor, `start --profile <profile>` checks
integrity and free pilot ports before loading the service. It never kills a port
owner. `check`, `status`, and `stop` accept the same profile. Stop remains usable
if the data volume/runtime is unavailable. Stop/start do not remove files or VPN
routes. A successful request to start is not readiness: confirm the app and bridge
health and the expected source in the private `service-status.json`.

The supervisor has a per-pilot kernel lock, private atomic status snapshots,
child-exit detection, and 15-second health checks. Three consecutive unhealthy
checks fail the supervisor; launchd restarts failed exits with a 30-second throttle.
Normal operator stop does not trigger recovery. launchd is configured to clean
up the job's process group rather than leave orphan listeners. These health checks
do not load models or perform synthesis. Crash recovery can interrupt an in-flight
request; recording drafts and completed voice segments remain the recovery source.
This is recovery from software faults, not protection against a sleeping/unplugged
Mac, a failed external disk, or a network outage. Current-login launchd registration
does not survive logout/reboot; login-start behavior requires separate approval.

The managed pilot was verified on 2026-10-27 using immutable release `442ff70`:
backend crash, supervisor crash, unresponsive backend, and normal stop/start all
recovered without orphan child processes or changed stored data. Full evidence
and limitations are recorded in `PENDING_HARDENING_REVIEW.md`. Missing-volume
behavior is unit-tested, not an actual drive-unplug test. The private pilot remains
deliberately limited; its queued phone recording is not processed by this launcher.
Logs currently append without automated retention. Do not interpret this pilot
registration as a production installation or reboot-start configuration.

### Local workload controls (candidate, not deployed)

The candidate admits only one heavyweight app-owned local operation at a time:
language generation, voice preparation, transcription, or memory indexing.
Nested operations in the same worker are allowed; competing requests fail with
a clear busy message. Embeddings remain available for retrieval, including
OpenAI Talk while local voice is busy. No automatic provider switching occurs.
The guard covers threads and processes sharing one container filesystem, not
independent containers or unrelated native CLI jobs. A live native bridge busy
check additionally protects against a voice job left running after an app restart.

Defaults are five-minute embedding residency, two-minute language-model
residency, 4096-token Talk context, and 8192-token analysis context. These are
configurable; context is input-plus-output capacity, not an answer-length target.
The new settings do not select a different model or change embedding formatting.
Whisper's cached instance is released after transcription. MLX weights and
in-memory conditioning are released after 120 idle seconds or before another
heavy local model loads. On-disk reference files and prepared WAV/segment caches
are preserved. The next uncached synthesis may therefore incur model loading.

Deploy the matching native voice bridge before the app: it adds the authenticated
`POST /model/unload` endpoint. An older loaded bridge is deliberately reported as
incompatible rather than running both large models together. Existing environment
overrides can retain older residency values; inspect them during release review.

Keep `LOCKS_DIR=/tmp/here-i-am-locks` and the local-inference lock on the container
filesystem. These are ephemeral coordination files, not memoir storage. Do not
run multiple independent app containers against the same library. The new scratch
Chroma failure documented in PENDING_HARDENING_REVIEW remains a release blocker.

### Recording drafts and bounded retries (candidate, not deployed)

Emitted recording chunks are saved to origin-scoped IndexedDB until the server
acknowledges saving the upload. Reopen the same site/browser profile to recover
a draft; recovery does not upload automatically. Conversation permission must
be confirmed again. Website-data clearing, browser eviction, and private mode
can remove drafts. Safari's single-blob MP4 path cannot persist audio before
the recorder emits its final blob, so this is not full crash protection during
an active recording. Keep the page open if the recovery-copy warning appears.
Only a finalized draft with every expected chunk is offered for retry. Incomplete
copies are retained with a warning, not silently treated as complete recordings.

Idempotent filesystem writes retry transient failures at most six times, with
under one second of backoff. Full-disk and permission errors fail immediately.
Missing processing state is not silently recreated. Saved source audio is
reread and matched against received bytes and SHA-256. Interrupted transfers
remain recoverable but are not ready memories. Upload retries after a lost
server acknowledgement can still create duplicate sessions; server-side
idempotent upload IDs remain follow-up work.
Atomic state writes additionally verify read-back visibility/content before
returning success. This mitigates observed delayed visibility; it does not
repair SQLite/Chroma behavior at the Docker/ExFAT filesystem boundary.

- Interrupted jobs are reported in job history and may be retried.
- Run reconciliation before and after maintenance.
- Restore authoritative files first; rebuild metadata/chunks/index afterward.
- Never copy a Chroma directory while it is being written. Prefer a stopped-app volume snapshot or rebuild from portable artifacts.
- Verify a backup without changing data using `python scripts/restore_backup.py <backup> <empty-target>`. Add `--confirm-empty-target` only when restoring into a genuinely empty directory. Restore never overwrites or deletes existing data.

## Historical Docker deployment gate

The checks below apply to the retained Docker deployment path only. They are not
authorization for a native cutover. For the candidate native architecture, follow
the staged production cutover plan in `PENDING_HARDENING_REVIEW.md`; keep production
unchanged until those separate compatibility and approval gates are complete.

Before replacing the existing container: run the test target, launch an isolated container with a synthetic empty data volume on another port, verify the UI and API, create a volume snapshot, and only then schedule a controlled cutover. Do not combine collection activation with the application rollout.

For a controlled cutover:

1. Record the current value returned by `/api/providers/status`.
2. Verify `OPENAI_MODEL` is present in `ALLOWED_OPENAI_MODELS` and keep `ALLOW_RUNTIME_CLOUD_KEY=false`.
3. Run the test image and synthetic-volume smoke test.
4. Create a stopped-app snapshot of `/Volumes/Personal/here-i-am`.
5. Rebuild through `scripts/start.sh`; do not build directly from AppleDouble-contaminated external-drive files.
6. Require HTTP 200 from both `/api/health` and `/api/ready` before opening Safari.
7. Switch once to each provider in Settings and confirm `/api/providers/status` reports the same active provider and `active_ready=true`.
8. Confirm the memory-batch endpoint still reports `openai_embedding_enabled: false`.
