# Voice and cloud consent contract

## Voice identity

Voice synthesis is disabled until the user confirms that they are the recorded speaker or have documented authority from that speaker. Consent records include timestamp, selected source sessions, provider, model, disclosure version, and revocation state.

Original recordings are immutable. The system creates a separate normalized reference artifact. Revocation disables synthesis immediately and can delete the derived reference and provider voice identifier without deleting autobiography recordings.

Generated speech is labeled “AI voice” in the interface. Auto-play is off by default. Users can stop speech immediately and continue reading captions.

## Cloud processing

Local processing is the default. Enabling a cloud model or cloud voice requires a separate explicit choice that explains what leaves the device. Only the current question, selected retrieved excerpts, minimum style instructions, and a bounded derived profile of vocabulary and speaking rhythm may be transmitted. The complete library, raw Chroma store, and unrelated recordings are never sent.

Cloud credentials are supplied through environment configuration or kept only in process memory. They are excluded from preferences, logs, backups, exports, and API responses. The UI shows a cloud badge for every cloud-generated answer or voice.

There is no silent local-to-cloud fallback. If a cloud service fails, the user chooses whether to retry locally.

## Audit and deletion

The application records provider, model, elapsed time, transmitted-context count, consent version, and success/failure without recording credentials. Feedback and generation audit files use append-only JSONL. Derived voice references and consent records have explicit status and deletion endpoints.
