# Security boundary

Here I Am is a single-user localhost application. Docker publishes the web service only on `127.0.0.1`; the Ollama and voice helpers must also remain loopback-only. Do not expose these ports to a LAN, reverse proxy, tunnel, or the public internet without adding user authentication and a separate threat-model review.

Production disables FastAPI documentation, runs the application as a non-root user in a read-only container, drops capabilities, rejects browser mutations from unapproved origins, limits decoded upload duration and size, and returns opaque resource identifiers rather than host paths. The two native mutation bridges require a launcher-generated secret header in addition to binding only to loopback.

OpenAI is optional and is used only for Talk composition. Embeddings, transcription, storage, and the local cloned voice do not use OpenAI. An OpenAI request contains the current question, selected excerpts, and a bounded derived speaking-style profile. Prefer `OPENAI_API_KEY_FILE` on a protected mount; never commit a credential or enter it into ordinary preferences.

Chroma is append-only. No application or maintenance path may delete a Chroma record. Revisions and archives are enforced through the active filesystem version manifest and retrieval filtering.

Report a suspected secret exposure, unexpected network listener, retrieval of an archived/superseded memory, or backup-integrity failure before continuing ordinary use.
