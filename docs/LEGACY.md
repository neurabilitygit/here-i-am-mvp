# Dormant prototypes

The production implementation is exclusively the root `app/` tree, excluding `app/app/`. The following tracked directories are historical prototypes and are not build inputs: `backend/`, `frontend/`, `worker/`, `app/app/`, `host_bridge/`, `host_helper/`, and `host_tools/`.

They remain in Git temporarily for historical comparison. Production changes, tests, deployment fixes, and security patches must not be applied there. Docker explicitly excludes them. A later repository-history cleanup may remove them after the production-hardening branch has completed its acceptance period.
