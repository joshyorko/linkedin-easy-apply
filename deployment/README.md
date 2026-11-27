# Private deployment

Use hosted qualification checks and a reviewed immutable source SHA. No workflow
in this repository schedules a homelab runner or receives private credentials.
Public pull-request code runs only on standard hosted runners with read-only
repository permissions. The private deployment is an operator-controlled Git
pull after trusted-source promotion, not a workstation source archive.

The ARM64 application target in `qualification/Dockerfile` uses the official
Actions Runtime1.1.2 CP312 manylinux wheel on pinned Python3.12.11 Bookworm. It
imports the real package during build without account state. The separate fixture
target verifies real synthetic HTTP/browser/MCP behavior and restart in CI.

Before deployment, verify the exact SHA's checks and review, fetch from canonical
origin into an isolated checkout, detach at that SHA and verify `git rev-parse HEAD`.
Build with `--file qualification/Dockerfile --target application`; record its
image ID and source SHA together. Set EASY_APPLY_IMAGE to that immutable image ID.
Never deploy an unreviewed pull-request ref or mutable image tag.

`deployment/compose.yaml` owns only one application service and its own state
volume. It creates no PostgreSQL server, proxy, tunnel or public ingress. Its
host network mode consumes an existing approved host-loopback database route;
the runtime entrypoint binds ONLY127.0.0.1 and requires independent authentication.
Do not use this mode to expose the service on another interface. Verify actual
listener scope and enforced memory/CPU before acceptance. Preserve other services.

The database owner provisions a dedicated least-privilege capability privately.
The database-service file and CA are read-only mounts; the service file must
require verify-full TLS and reference `/run/secrets/database-ca`. Keep its actual
path/values out of Git, build arguments, CI logs and chat. Runtime auth uses a
different protected file. Files must be readable only by the mapped service user,
UID10001, and runtime must never print their contents. No LinkedIn account/profile
or OpenAI credential is needed for synthetic acceptance.

Start only this Compose project after its owner-provisioned prerequisites exist.
Verify unauthorized rejection, tool catalog, live-submit rejection with synthetic
inputs, harmless synthetic database checks, browser fixture and MCP list/call.
Restart the same service and verify auth, retained state and catalog again. Never
invoke real login, search, enrichment or application submission during acceptance.
Executor registration is a separate integration gate after service health.

Retain the previous image ID/source SHA and state backup before updates. Database
schema/runtime migrations can make rollback unsafe: stop the service and use its
matched state backup rather than assuming an older image can read newer data.
Never delete a volume or overwrite another service's data as part of rollout.
