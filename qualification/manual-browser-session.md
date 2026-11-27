# Manual browser session qualification

## Isolation and sandbox

The Pi UI uses a fresh display with Xauthority, no X11 TCP listener, and a private
0700 directory containing its RFB Unix socket. RFB has no TCP listener. noVNC binds
only Pi loopback; SSH forwards it only to T3-host loopback. This assumes trusted
local users/processes on those hosts: loopback HTTP is not a multiuser auth boundary.
There is no permanent listener, tunnel service, X access-control bypass, privileged
container, added browser capability, host seccomp change, or sandbox fallback.

The browser runs as image UID 10001, with all container capabilities dropped,
no-new-privileges, a read-only root, bounded CPU/memory/PIDs, a temporary HOME and
only the persistent browser subdirectory mounted. The browser's SingletonLock and
the helper's nonblocking flock protect the profile. The owner maintenance window
prevents uncooperative service startup races. The helper never clears stale browser
locks; an unclean shutdown requires separate owner diagnosis.

`browser-seccomp.json` is derived from Microsoft's Playwright Docker policy:
<https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json>.
Upstream content SHA-256 at retrieval:
`cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`.
The only syscall addition is `chroot` alongside the upstream namespace allowances;
with all outer capabilities dropped, Chromium needs it inside its user namespace.
The default remains `SCMP_ACT_ERRNO`. The Apache license is retained next to it.
This policy applies only to each disposable/session container, never the daemon.

## Qualification receipt (2026-11-27)

The actual ARM64 application image was inspected, not inferred from the root
amd64 Dockerfile. Image ID:
`sha256:08b39aaf53a7eeea73f2e6198cc047ed6e7412a05ba42b7c5956c652a69d5da7`.
Its image revision label and deployed source HEAD both identify
`c2eb10c31ba352155a20f374fb1f1ead360a06b6`.
The deployed image contains `robocorp-browser==2.3.5` and full ARM64 Chromium 1255.
The pinned source's persistent `context(**kwargs)` forwards kwargs into the launch
path; launch-only options belong in `browser.context(...)`, not
`browser.configure(args=...)`. The manual path uses the same installed Chromium
directly so it needs neither an Actions task nor an automation/debug connection.
Synthetic tests use Playwright already present in that exact image.

Observed sequentially, without concurrent heavy runs:

- Default Docker seccomp: raw non-root Chromium failed `No usable sandbox`.
- Upstream Playwright policy: sandboxed synthetic rendering passed with adequate
  PID headroom. Dropping all outer capabilities initially exposed the missing
  namespace `chroot` allowance; the checked-in policy resolves that exact failure.
- Full private-UI launcher: noVNC returned HTTP 200 and `ss` confirmed only
  `127.0.0.1:6088`; the synthetic browser was reached through T3's incognito preview
  at the noVNC URL. That preview was subsequently closed. This proves UI transport,
  not T3 project-action discovery or a real login.
- `chrome://sandbox` reported namespace sandbox, PID/network namespaces,
  Seccomp-BPF/TSYNC, and `You are adequately sandboxed.` in both full-Chromium modes.
- Account-free local HTML rendered in the headed browser; localStorage survived
  clean close and headless reopen of the same disposable profile. Cookies remained
  absent. A competing process was rejected by the held profile lease.
- A second disposable profile exposed DevTools **inside network-none container
  loopback only**; its version endpoint and synthetic CDP screenshot passed. No
  port was published or forwarded. This can diagnose synthetic headless visibility,
  but is not the manual sign-in solution because authenticated DevTools is prohibited.
- Normal closure and controller SIGTERM removed the owned containers, temporary
  volumes, UI listeners and remote scratch. Occupied T3-host port 6088 failed closed
  and preserved the existing listener. The real running-service guard rejected
  manual mode before profile access or UI startup. Existing services were preserved.
- Four local standard-library boundary tests passed: wrong host, wrong image,
  unresolved route, and a running profile consumer all start no UI.
- The existing five-entrypoint live-submit rejection test passed in the exact
  deployed image with network none and no account mounts. The host's Python lacks
  `actions`, so its initial attempt could not run that existing test; no dependency
  was installed on the host to work around it.

Reproduce only the account-free proof from the T3 execution host:
`python3 scripts/manual_browser_session.py --synthetic`.
It uses a randomly named throwaway Docker volume, network none, local HTML and
automatic teardown. Never replace that volume with the real profile for testing.
Local boundary tests: `python3 -m unittest discover -s tests -p test_manual_browser_session.py -v`.

Executor authentication and repository splitting are outside this change.
