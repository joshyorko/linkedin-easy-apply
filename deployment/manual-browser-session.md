# Private manual sign-in

Status: synthetic ARM64 qualification passed; real sign-in is **not yet accepted**.
The running service currently reserves the profile, so the action deliberately
refuses to open it. No service was stopped, no account was used, and no application
was submitted during qualification.

## User flow

After the prerequisites below are satisfied, select **Sign in to LinkedIn** in
T3's project scripts menu. Open the loopback URL printed in its terminal. Sign in
and finish MFA inside that browser only, then close all browser tabs. The browser
exits, the UI and SSH forward stop, and the exclusive profile lease is released.
The session expires after 20 minutes. Stopping the action also cleans up its UI.
Normal browser closure is preferable for flushing profile changes; interruption
or timeout does not guarantee the last changes were persisted.

The equivalent single command, from this repository on the **T3 execution host**,
is `python3 scripts/manual_browser_session.py`.

The action never asks for LinkedIn credentials, reads cookies, records the screen,
exports account state, or imports/calls application actions. Only the browser
itself manages the persistent profile. Clipboard transfer is disabled. The manual
browser has no DevTools port or automation connection.

## One-time prerequisites and remaining acceptance gates

- On the T3 execution host, the operator-owned `~/.ssh/config` must contain the
  approved `pi5-02` alias, identity, and an independently verified existing host
  key. The launcher requires strict key checking and noninteractive authentication.
  It does not accept unknown keys, passwords, an alternate host, or agent forwarding.
- Pi5-02 must retain the exact deployed image/source pins in
  `scripts/manual_browser_session.py`, Docker access, TigerVNC, xauth, websockify
  and `/usr/share/novnc`. These were already installed; the action installs nothing.
  Image changes require requalification and a reviewed pin update.
- The owner must arrange an exclusive maintenance window for the
  `easy-apply-private_state` volume. **Every container using that volume must remain
  stopped throughout sign-in.** This action refuses running consumers and never
  stops or restarts services. Do not start automation until the action reports that
  its lease was released. The deployed application predates a cooperative lease;
  this maintenance prerequisite cannot safely be removed by a UI launcher alone.
  No running service was changed to satisfy this gate.
- If T3 runs on a remote machine, privately forward its loopback port 6088 to the
  human's browser, for example with VS Code's private Ports facility. This is a
  one-time host/browser connectivity prerequisite, not a public ingress setup.
  An occupied local or remote port fails closed; existing listeners are preserved.
- Import the root `t3.json` project script after this change is installed in the
  registered project checkout. The spelling is **t3.json**, at the repository root.
  The file validates against <https://t3.codes/schema/t3.json> using the installed
  T3 Zod validator. Its fields also match the installed T3
  `0.1.14-nightly.20261127.5332` project schema. No real sibling `t3.json` examples
  were found in the scoped local project searches. Actual T3 menu discovery and
  clicking the imported action remain unverified: the registered project points
  outside this authorized worktree, and its saved-script catalog is currently empty.
  Only this worktree was edited; no replacement project or duplicate owner was made.

After those gates, acceptance is Josh selecting the action and manually completing
sign-in/MFA and normal closure. Do not ask an agent to inspect the signed-in UI.
Live submission remains disabled independently of browser sign-in.

See [the isolation and qualification receipt](../qualification/manual-browser-session.md) for the exact image, sandbox policy, tests, and remaining verification limits.
