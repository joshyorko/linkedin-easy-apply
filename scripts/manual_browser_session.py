#!/usr/bin/env python3
"""Single-use human UI. Never imports application actions or reads login state."""

import argparse
import io
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

IMAGE = "sha256:08b39aaf53a7eeea73f2e6198cc047ed6e7412a05ba42b7c5956c652a69d5da7"
SOURCE = "c2eb10c31ba352155a20f374fb1f1ead360a06b6"
CHROME = "/var/lib/easy-apply/home/.cache/ms-playwright/chromium-1255/chrome-linux-arm64/chrome"
PORT = 6088
VOLUME = "easy-apply-private_state"
SSH = ["ssh", "-F", str(Path.home() / ".ssh/config"), "-o", "BatchMode=yes",
       "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no",
       "-o", "PasswordAuthentication=no", "-o", "ConnectTimeout=10"]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def local(synthetic):
    # Resolve only the existing operator-owned alias; never accept unknown keys.
    config = run(*SSH, "-G", "pi5-02", capture_output=True, text=True).stdout
    fields = dict(line.split(" ", 1) for line in config.splitlines() if " " in line)
    if fields.get("hostname") == "pi5-02" or not fields.get("identityfile"):
        raise RuntimeError("One-time setup: configure the approved pi5-02 SSH alias and verify its host key out of band.")
    root = Path(__file__).resolve().parents[1]
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        archive.add(__file__, arcname="session.py")
        archive.add(root / "deployment/browser-seccomp.json", arcname="browser-seccomp.json")
    # This task's payload is ephemeral; it never installs into a running service.
    mode = " --synthetic" if synthetic else ""
    upload = (
        "set -eu; umask 077; d=$(mktemp -d /tmp/codex-easy-apply-session-XXXXXXXX); "
        'trap \'rm -rf "$d"\' EXIT; tar -xf - -C "$d"; printf "%s\\n" "$d"; trap - EXIT'
    )
    directory = run(*SSH, "pi5-02", upload, input=payload.getvalue(), capture_output=True).stdout.decode().strip()
    if not directory.startswith("/tmp/codex-easy-apply-session-") or not directory.replace("/", "").replace("-", "").isalnum():
        raise RuntimeError("Remote scratch path was not valid.")
    command = f"trap 'rm -rf {directory}' EXIT; python3 {directory}/session.py --remote" + mode
    process = subprocess.Popen(
        [*SSH, "-tt", "-o", "ExitOnForwardFailure=yes", "-L",
         f"127.0.0.1:{PORT}:127.0.0.1:{PORT}", "pi5-02", command],
        stdin=subprocess.DEVNULL,
    )
    try:
        process.wait()
        if process.returncode:
            raise RuntimeError(f"Private session did not complete (exit {process.returncode}).")
    finally:
        stop(process)
        subprocess.run([*SSH, "pi5-02", f"rm -rf {directory}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remote(synthetic):
    if socket.gethostname().split(".")[0].lower() != "pi5-02":
        raise RuntimeError("Refusing a host other than the approved pi5-02.")
    image = json.loads(run("docker", "image", "inspect", IMAGE, capture_output=True, text=True).stdout)[0]
    if image["Architecture"] != "arm64" or image["Config"]["Labels"].get("org.opencontainers.image.revision") != SOURCE:
        raise RuntimeError("Deployed ARM64 image/source pin does not match.")
    if not synthetic:
        # The deployed image predates a cooperative automation lease. Refuse while
        # ANY running container can access the volume, even if Chromium is idle.
        users = run("docker", "ps", "-q", "--filter", f"volume={VOLUME}", capture_output=True, text=True).stdout
        if users.strip():
            raise RuntimeError("Profile is reserved by a running service. Owner must arrange a maintenance window first; this action never stops services.")
        run("docker", "volume", "inspect", VOLUME, stdout=subprocess.DEVNULL)
    root = Path(__file__).resolve().parent
    name = "easy-apply-manual-" + secrets.token_hex(8)
    vnc = web = browser = None
    temporary_volume = name + "-profile"
    volume_created = False
    try:
        with tempfile.TemporaryDirectory(prefix="ui-", dir=root) as directory:
            directory = Path(directory)
            auth = directory / "Xauthority"
            auth.touch(mode=0o644)
            display = next((n for n in range(80, 100) if not Path(f"/tmp/.X{n}-lock").exists() and not Path(f"/tmp/.X11-unix/X{n}").exists()), None)
            if display is None:
                raise RuntimeError("No unused private display; existing sessions were preserved.")
            # Cookie goes to a private file, not an argument, terminal, or log.
            run("xauth", "-f", str(auth),
                input=f"add :{display} . {secrets.token_hex(16)}\n".encode(), stdout=subprocess.DEVNULL)
            auth.chmod(0o644)  # Parent remains 0700; only this file enters the container.
            vnc = subprocess.Popen([
                "Xtigervnc", f":{display}", "-geometry", "1280x800", "-depth", "24",
                "-auth", str(auth), "-nolisten", "tcp", "-localhost", "yes",
                "-rfbport", "-1", "-rfbunixpath", str(directory / "rfb"),
                "-SecurityTypes", "None", "-AcceptCutText", "0", "-SendCutText", "0",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                if (directory / "rfb").exists():
                    break
                if vnc.poll() is not None:
                    raise RuntimeError("Private display failed to start.")
                time.sleep(0.05)
            else:
                raise RuntimeError("Private display readiness timed out.")
            web = subprocess.Popen([
                "websockify", "--web=/usr/share/novnc", "--unix-target=" + str(directory / "rfb"),
                f"127.0.0.1:{PORT}",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            if web.poll() is not None:
                raise RuntimeError("Private UI port is occupied or noVNC is unavailable.")
            if synthetic:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/vnc.html", timeout=5) as response:
                    assert response.status == 200
                listeners = run("ss", "-ltnH", "sport", "=", f":{PORT}", capture_output=True, text=True).stdout
                assert listeners and all(line.split()[3] == f"127.0.0.1:{PORT}" for line in listeners.splitlines()), listeners
                print("PASS: noVNC HTTP ready; only host-loopback listener", flush=True)
            if synthetic:
                run("docker", "volume", "create", temporary_volume, stdout=subprocess.DEVNULL)
                volume_created = True
                run("docker", "run", "--rm", "--network", "none", "--user", "0", "--cap-drop", "ALL",
                    "--cap-add", "CHOWN", "--mount", f"type=volume,src={temporary_volume},dst=/profile",
                    "--entrypoint", "chown", IMAGE, "10001:10001", "/profile")
                mount = f"type=volume,src={temporary_volume},dst=/profile"
            else:
                mount = f"type=volume,src={VOLUME},dst=/profile,volume-subpath=browser_context"
            command = [
                "docker", "run", "--rm", "--init", "--name", name,
                "--hostname", socket.gethostname(),
                "--read-only", "--memory", "768m", "--cpus", "1", "--pids-limit", "512",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--security-opt", f"seccomp={root / 'browser-seccomp.json'}",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--env", "HOME=/tmp",
                "--env", "PLAYWRIGHT_BROWSERS_PATH=/var/lib/easy-apply/home/.cache/ms-playwright",
                "--env", f"DISPLAY=:{display}", "--env", "XAUTHORITY=/run/Xauthority",
                "--mount", mount,
                "--mount", f"type=bind,src={auth},dst=/run/Xauthority,readonly",
                "--mount", f"type=bind,src=/tmp/.X11-unix/X{display},dst=/tmp/.X11-unix/X{display},readonly",
            ]
            if synthetic:
                command += ["--network", "none"]
            command += ["--entrypoint", "python", IMAGE, "-c", worker_source(synthetic)]
            print(f"Open http://127.0.0.1:{PORT}/vnc.html?autoconnect=1&resize=scale", flush=True)
            print(f"If T3 runs remotely, privately forward port {PORT} from the T3 host in VS Code. Never make it public.", flush=True)
            print("Sign in and finish MFA in the browser only. Close all browser tabs when finished. UI expires in 20 minutes.", flush=True)
            browser = subprocess.Popen(command)
            browser.wait(timeout=90 if synthetic else 1200)
            if browser.returncode:
                raise RuntimeError("Browser failed; no unsafe fallback was attempted.")
    finally:
        # Remove only the randomly named container belonging to this invocation.
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stop(browser)
        stop(web)
        stop(vnc)
        if volume_created:
            run("docker", "volume", "rm", temporary_volume, stdout=subprocess.DEVNULL)
    print("Private UI closed; exclusive profile lease released.", flush=True)


def worker_source(synthetic):
    prefix = """
import fcntl, subprocess
lease = open('/profile/.manual-session.lock', 'a')
fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
"""
    if not synthetic:
        return prefix + f"""
subprocess.run([{CHROME!r}, '--user-data-dir=/profile', '--no-first-run', '--disable-dev-shm-usage', 'https://www.linkedin.com/login'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
"""
    return prefix + """
from pathlib import Path
from playwright.sync_api import sync_playwright
probe = subprocess.run(['python', '-c', "import fcntl; f=open('/profile/.manual-session.lock','a'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
assert probe.returncode != 0, 'Concurrent profile lease was accepted'
fixture = Path('/tmp/synthetic.html')
fixture.write_text('<title>Synthetic manual session</title><h1>No account state</h1>')
with sync_playwright() as p:
    for headless in [False, True]:
        with p.chromium.launch_persistent_context('/profile', executable_path='/var/lib/easy-apply/home/.cache/ms-playwright/chromium-1255/chrome-linux-arm64/chrome', headless=headless, chromium_sandbox=True) as c:
            page = c.pages[0]
            page.goto('chrome://sandbox')
            status = page.locator('body').inner_text()
            assert 'Layer 1 Sandbox' in status and 'Namespace' in status and 'Seccomp-BPF sandbox' in status, status
            assert 'You are adequately sandboxed.' in status, status
            page.goto(fixture.as_uri())
            assert page.title() == 'Synthetic manual session'
            assert not c.cookies(), 'Unexpected account state in disposable profile'
            if not headless:
                page.evaluate("localStorage.setItem('synthetic', 'retained')")
                print('Synthetic UI ready (30 seconds)', flush=True)
                page.wait_for_timeout(30000)
            else:
                assert page.evaluate("localStorage.getItem('synthetic')") == 'retained'
    # A DevTools port is tested ONLY on a second disposable profile, inside
    # network-none loopback. It is never published, forwarded, or reused.
    import json, urllib.request
    with p.chromium.launch_persistent_context('/tmp/devtools-disposable', executable_path='/var/lib/easy-apply/home/.cache/ms-playwright/chromium-1255/chrome-linux-arm64/chrome', headless=True, chromium_sandbox=True, args=['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0']) as c:
        page = c.pages[0]
        page.goto(fixture.as_uri())
        port = int(Path('/tmp/devtools-disposable/DevToolsActivePort').read_text().splitlines()[0])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version') as response:
            assert 'Browser' in json.load(response)
        assert c.new_cdp_session(page).send('Page.captureScreenshot')['data']
    print('PASS: exclusive lease rejection, headed sandbox, synthetic page, clean close, headless reopen, profile persistence, disposable-only loopback DevTools screenshot', flush=True)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Use only disposable account-free state and network none")
    parser.add_argument("--remote", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise RuntimeError("Session interrupted; cleaning up owned resources.")
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        (remote if args.remote else local)(args.synthetic)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        print(f"Session stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
