# Here I Am: Immersive Experience Plan

## Product intent

Here I Am should feel like entering a living room with a familiar person, not operating an AI administration console. The primary audience is an adult over 55 who may have reduced vision, dexterity, hearing, confidence with technology, or short-term memory. The product therefore exposes three stable choices: **Talk**, **Remember**, and **Memories**. Technical operations move behind a clearly marked settings surface.

## Experience concept: The Living Portrait

The home screen is a full-screen animated portrait surrounded by a slow-moving field of memory lights. The portrait communicates system state through motion:

- **resting**: slow breathing halo;
- **listening**: expanding rings and live microphone waveform;
- **thinking**: orbiting memory lights;
- **speaking**: audio-reactive mouth, glow, and caption reveal;
- **needs attention**: still portrait and a single plain-language action.

Every state must also have a text label and accessible live-region announcement. Motion is never the only signal, and a persistent reduce-motion control freezes decorative animation.

## Navigation

1. **Talk** opens a conversational scene with voice or keyboard question input.
2. **Remember** opens a recording scene with one large record control, elapsed time, pause, and save.
3. **Memories** opens a visual card carousel with search, playback, transcript review, and export.

The application saves completed recordings into a visible local queue. The user proactively starts a confirmed batch after being warned that Here I Am will be unavailable until local processing finishes.

## Delivery stages and acceptance gates

### Stage 1: Baseline and safety

- Preserve existing session and Chroma contracts.
- Capture time to acknowledgment, first token, complete answer, and first audio.
- Add explicit consent and revocation contracts for voice cloning and cloud processing.
- Create a representative evaluation question set without exposing it to generated answers.

Gate: existing tests pass and original recordings have not been modified.

### Stage 2: Immersive interface

- Replace the dashboard with the Living Portrait and three-scene navigation.
- Add large targets, text scaling, strong contrast, captions, reduced motion, consistent Back/Home controls, onboarding, and plain-language recovery.
- Add a local SVG avatar builder and persistent avatar preferences.

Gate: primary tasks are completable at 200% zoom, by keyboard, and with reduced motion.

### Stage 3: Fast, provider-independent conversation

- Stream local Ollama tokens to the browser.
- Keep the active model warm and remove the model-based routing call.
- Add a provider interface for local Ollama and optional OpenAI-compatible cloud generation.
- Keep retrieval and personal storage local; send only selected context when cloud mode is explicitly enabled.

Gate: warm first text is materially faster than the baseline and cloud use is always visible.

### Stage 4: Speaker fidelity

- Derive a quantitative fingerprint from reviewed transcripts and audio timing.
- Retrieve context-specific style exemplars.
- Separate grounding instructions from style realization and record source evidence.
- Add answer feedback and a repeatable evaluation contract.

Gate: factual grounding does not regress and blind similarity ratings improve.

### Stage 5: Consented voice synthesis

- Score existing recordings as possible references without changing them.
- Create a derived, normalized reference only after explicit rights confirmation.
- Support a native local Qwen3-TTS bridge and an optional ElevenLabs voice.
- Add play, pause, stop, replay, captions, speed, auto-play opt-in, disclosure, and voice deletion.

Gate: the speaker or authorized owner approves a fixed test set for intelligibility and identity fidelity.

### Stage 6: Audio-reactive portrait

- Drive portrait speaking states from actual audio energy.
- Add approximate viseme classes when the selected TTS provider exposes timing.
- Preserve captions and reduced-motion behavior.

Gate: animation improves recognition and engagement in user testing without reducing trust.

## Product metrics

- Task completion: ask a question, record a memory, find a memory.
- Mis-taps, backtracks, and requests for help.
- Time to first text and first audio.
- Grounded-answer accuracy and unsupported-claim rate.
- Speaker-similarity rating, vocabulary match, sentence-rhythm match, and perceived authenticity.
- Voice-consent completion, revocation success, and cloud-disclosure comprehension.

## Non-goals

- No photorealistic deepfake avatar in the first release.
- No silent upload of recordings or transcripts to any cloud provider.
- No automatic voice-clone creation during startup or migration.
- No removal of text captions in favor of audio-only interaction.
