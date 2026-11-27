# Private native qualification fixture

Prepared only. Do not start this fixture until the verified new Actions Runtime
1.1.2 public artifact/provenance receipt, target compatibility and any shared-host
runtime window are established. No old candidate artifact is an acceptable substitute.

This directory is a separate synthetic action package. It does not import the
application, load accounts, use PostgreSQL or start tunnels. It contains only an
echo action and a browser action that fills inline HTML while denying browser
network requests. It has no submission button or external endpoint declarations.

The reproduction `qualification/Dockerfile` pins CPython3.12.11 Bookworm ARM64
and the verified official1.1.2 CP312 manylinux wheel SHA-256. Its default target is the disposable fixture; the separate `application`
target imports the real package and uses `deployment/start.sh`. The Dockerfile itself is not build-qualified: the matching base/wheel path
was installed and tested inside a disposable native capped container instead.
Use `--init`: without an init/reaper, the observed worker retirement failed with
pidfd_open EINVAL and blocked MCP execution. With init, the full synthetic gate
passed without a runtime byte change. Install libatomic1 before the Playwright
dependency installer; its native Node executable requires libatomic.so.1.
Build from the repository root only within a coordinated runtime window.
Publish container ports only to host loopback, use a separate temporary datadir
and independently generated runtime credential, and keep one worker. Never use
host networking or mount account/session state. The browser/system dependency
list remains subject to actual target image build and browser-launch checks.

For the exact target, verify architecture, dynamic linker/GLIBC and Python ABI
before selecting a standalone binary or Python wheel. Verify artifact SHA-256
against public release provenance. Qualify the application package separately
with `scripts/qualify_offline.py` and the selected runtime's package importer.

After those gates, use the selected verified executable's help to confirm import
and start flags. Keep separate temporary HOME, ROBOCORP_HOME, ACTIONS_HOME,
SEMA4AI_HOME, browser cache, output and datadir for qualification. Do not attach
existing datadirs or browser profiles. Install Chromium in the matching resolved
environment as the runtime user, with the required OS libraries and sandbox.

Start only this fixture on a confirmed free loopback port with authentication,
one worker and no public exposure. Do not invoke the repository Compose stack.
Verify unauthorized rejection, advertised action schemas, synthetic_echo result
`easy-apply-fixture:synthetic`, then synthetic_browser result `true`. Negotiate MCP
at `/mcp`, list tools and call only the synthetic echo. Preserve protocol/session
headers and support JSON or event-stream responses. Health alone is not acceptance.

Stop the owned listener and worker before deleting owned temporary state. Record
exact source/artifact/interpreter/dependency identities, selected architecture,
browser version, assertions, listener scope and cleanup. None of these prepared
steps constitutes native runtime, browser or production qualification yet.
