# Security exceptions

## Embedded Chroma advisories

The pinned `chromadb==0.5.23` dependency is currently reported under
PYSEC-2026-3813, PYSEC-2026-3814, and PYSEC-2026-3815. The upstream advisories
do not yet identify a fixed version.

They concern Chroma's authenticated network server: cross-tenant authorization
and an update-collection path that can accept a remote model repository. Here I
Am does not run or expose that server. It creates an in-process
`chromadb.PersistentClient` over the private application data directory, has one
collection namespace, and never accepts a model repository or
`trust_remote_code` value through its API.

CI therefore ignores only these three no-fix findings while enforcing the
embedded-client boundary with a static contract test. Remove the ignores and
upgrade Chroma as soon as an upstream fixed release is available. Any future
move to a Chroma network service or multi-tenant storage invalidates this
exception and must block release until the advisories are remediated.
