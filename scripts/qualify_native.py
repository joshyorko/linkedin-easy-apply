"""Disposable public-fixture qualification; never loads application/accounts."""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(os.environ.get('EASY_APPLY_QUALIFICATION_ROOT', '/qual'))
HOME = ROOT / 'home'
FIXTURE = os.environ.get('EASY_APPLY_FIXTURE_DIR', '/qual/fixture')
BASE = 'http://127.0.0.1:8080'


def main():
    os.umask(0o077)
    HOME.mkdir(parents=True, exist_ok=True)
    (ROOT / 'datadir').mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(HOME=str(HOME), ACTIONS_HOME=str(HOME / '.actions'),
               SEMA4AI_HOME=str(HOME / '.actions'), ROBOCORP_HOME=str(HOME / '.actions'),
               TMPDIR=str(HOME / 'tmp'), SEMA4AI_OPTIMIZE_FOR_CONTAINER='1')
    (HOME / 'tmp').mkdir(exist_ok=True)
    key = secrets.token_hex(32)
    (HOME / 'runtime-key').write_text(key)
    with (HOME / 'import.log').open('w') as log:
        subprocess.run(['action-server', 'import', '--dir', FIXTURE,
                        '--datadir', str(ROOT / 'datadir')], env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=1200)
    receipt = {'package_import': True, 'unauthorized_rejected': False,
               'http_echo': False, 'browser': False, 'mcp_echo': False}
    headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json, text/event-stream'}

    def request(path, body=None, auth=True, extra=None):
        h = dict(headers if auth else {'Accept': 'application/json, text/event-stream'})
        h.update(extra or {})
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            h['Content-Type'] = 'application/json'
        def deadline_expired(*args):
            raise TimeoutError('Synthetic request exceeded absolute 180-second deadline')
        previous = signal.signal(signal.SIGALRM, deadline_expired)
        signal.alarm(180)
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=h), timeout=180) as r:
                if r.headers.get('Content-Type', '').startswith('text/event-stream'):
                    for line in r:
                        if line.startswith(b'data:'):
                            value = json.loads(line[5:].strip())
                            if 'result' in value or 'error' in value:
                                return value, dict(r.headers)
                    raise AssertionError('SSE stream ended without a JSON-RPC result')
                raw = r.read().decode()
                return (json.loads(raw) if raw else None), dict(r.headers)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    with (HOME / 'server.log').open('w') as log:
        server = subprocess.Popen(['action-server', 'start', '--address', '0.0.0.0',
                                   '--port', '8080', '--dir', FIXTURE,
                                   '--datadir', str(ROOT / 'datadir'), '--actions-sync=false',
                                   '--min-processes', '1', '--max-processes', '1',
                                   '--api-key', key], env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 180
            while True:
                try:
                    schema, _ = request('/openapi.json')
                    break
                except (urllib.error.URLError, TimeoutError):
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Fixture startup failed; private server log retained')
                    time.sleep(1)
            def action_path(name):
                paths = [p for p in schema['paths'] if name in p.replace('-', '_') and p.endswith('/run')]
                assert len(paths) == 1, paths
                return paths[0]
            echo_path = action_path('synthetic_echo')
            try:
                request(echo_path, {'message': 'synthetic'}, auth=False)
            except urllib.error.HTTPError as error:
                assert error.code in (401, 403), error.code
                receipt['unauthorized_rejected'] = True
            assert receipt['unauthorized_rejected']
            result, _ = request(echo_path, {'message': 'synthetic'})
            assert result == 'easy-apply-fixture:synthetic', result
            receipt['http_echo'] = True
            result, _ = request(action_path('synthetic_browser'), {})
            assert result is True, result
            receipt['browser'] = True
            init, response_headers = request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'easy-apply-synthetic', 'version': '1'}}})
            assert 'result' in init, init
            session = next((v for k, v in response_headers.items() if k.lower() == 'mcp-session-id'), None)
            negotiated = init['result']['protocolVersion']
            mcp_headers = {'MCP-Protocol-Version': negotiated}
            if session:
                mcp_headers['Mcp-Session-Id'] = session
            request('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, extra=mcp_headers)
            listed, _ = request('/mcp', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, extra=mcp_headers)
            tools = [t for t in listed['result']['tools'] if 'synthetic_echo' in t['name'].replace('-', '_')]
            assert len(tools) == 1, listed
            called, _ = request('/mcp', {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                'params': {'name': tools[0]['name'], 'arguments': {'message': 'synthetic'}}}, extra=mcp_headers)
            assert not called.get('result', {}).get('isError'), called
            assert 'easy-apply-fixture:synthetic' in json.dumps(called), called
            receipt.update(mcp_echo=True, protocol=negotiated)
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
            receipt['server_stopped'] = server.poll() is not None
            (HOME / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
