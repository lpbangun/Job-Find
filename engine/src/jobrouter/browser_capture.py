"""Worker bridging Node/Playwright observations to the existing PublicFetcher.

All browser network is offline and fulfilled through this read-only HTTP path.
The outer bounded command runner owns the deadline and process-group cleanup.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from .models import now
from .transport import PublicFetcher, canonical_url


def capture(request):
    started = now()
    deadline = time.monotonic() + request['timeout']
    target = request['target']
    allowed = frozenset(request['allowed_hosts'])
    fixture = request.get('fixture_html')
    total_bytes = 0
    request_count = 0
    problems = []
    browser_problems = []
    resources = []
    stage = "worker_start"
    renderer_stage = "configuration"
    fetcher = PublicFetcher(budget=request['request_budget'], timeout=min(20, request['timeout']),
                            max_bytes=request['max_response_bytes'],
                            trusted_proxy_hosts=request['trusted_proxy_hosts'])
    def progress(complete=False):
        path = Path(request['progress_path'])
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'fetch_receipts': fetcher.receipts,
                             'resource_receipts': resources, 'accounting_complete': complete,
                             'stage': stage, 'renderer_stage': renderer_stage, 'browser_problems': browser_problems}))
        temporary.replace(path)
    progress()
    process = subprocess.Popen([request['node_executable'], str(Path(__file__).with_suffix('.mjs'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        process.stdin.write(json.dumps(request) + '\n')
        process.stdin.flush()
        while time.monotonic() < deadline:
            line = process.stdout.readline(2_000_001)
            if not line or len(line) > 2_000_000:
                raise ValueError('Browser worker exited or exceeded output limit')
            message = json.loads(line)
            if message.get('kind') == 'stage':
                renderer_stage = str(message.get('stage', 'unknown'))[:100]
                stage = 'renderer_wait'
                progress()
                continue
            if message.get('kind') == 'result':
                renderer_stage = str(message.get('stage', renderer_stage))[:100]
                stage = 'renderer_result'
                browser_problems = message.get('problems', [])
                progress()
                if message.get('error'):
                    raise ValueError(message['error'])
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if process.returncode != 0:
                    raise ValueError('Browser worker failed')
                raw = message['rendered_html'].encode()
                complete = not any(r['status'] == 'pending' for r in resources) and message.get('pending_requests', 0) == 0
                if not complete:
                    raise ValueError('Required browser requests remain pending')
                progress(complete=complete)
                return {'nonce': request['nonce'], 'provider': 'node-playwright-chromium',
                        'source_kind': 'fixture' if fixture is not None else 'live',
                        'browser_version': message['browser_version'], 'session_id': message['session_id'], 'started_at': started, 'observed_at': now(),
                        'target': target, 'snapshot': message['snapshot'],
                        'rendered_html': message['rendered_html'], 'rendered_sha256': hashlib.sha256(raw).hexdigest(),
                        'problems': problems + message['problems'], 'browser_problems': message['problems'], 'fetch_receipts': fetcher.receipts,
                        'resource_receipts': resources, 'accounting_complete': complete, 'bytes': total_bytes,
                        'stage': stage, 'renderer_stage': renderer_stage}
            if message.get('kind') != 'request':
                raise ValueError('Unsupported browser message')
            reply = {'id': message['id']}
            reason_code = 'fetch_failed'
            try:
                request_count += 1
                stage = 'resource_policy'
                resources.append({'url': str(message['url'])[:8192], 'status': 'pending',
                                  'method': str(message.get('method', 'unknown'))[:20],
                                  'resource_type': str(message.get('resource_type', 'unknown'))[:40],
                                  'renderer_stage': str(message.get('stage', renderer_stage))[:100],
                                  'started_at': now()})
                progress()
                if request_count > request['request_budget']:
                    reason_code = 'request_budget'
                    raise ValueError('Browser resource request budget exhausted')
                if len(message['url']) > 8192:
                    reason_code = 'url_limit'
                    raise ValueError('Browser resource URL exceeds limit')
                reason_code = 'invalid_url'
                url = canonical_url(message['url'])
                if message['method'] != 'GET':
                    reason_code = 'method_denied'
                    raise ValueError('Browser request method rejected')
                if urlsplit(url).hostname not in allowed:
                    reason_code = 'host_denied'
                    raise ValueError('Browser request host rejected')
                reason_code = 'fetch_failed'
                stage = 'resource_fetch'
                progress()
                if fixture is not None:
                    if url != target['application_url'] or message['resource_type'] != 'document':
                        reason_code = 'fixture_resource_denied'
                        raise ValueError('Fixture attempted external resource')
                    body, status, headers = fixture.encode(), 200, {'content-type': 'text/html; charset=utf-8'}
                else:
                    fetcher.timeout = min(20, max(0.001, deadline - time.monotonic()))
                    response = fetcher.get(url, follow_redirects=False)
                    if response.url != url:
                        reason_code = 'redirect_denied'
                        raise ValueError('Redirect requires a separately verified target')
                    body, status = response.body, response.status
                    headers = {k: v for k, v in response.headers.items()
                               if k not in ('set-cookie', 'content-encoding', 'content-length', 'transfer-encoding')}
                total_bytes += len(body)
                if len(body) > request['max_response_bytes'] or total_bytes > request['max_total_bytes']:
                    reason_code = 'byte_limit'
                    raise ValueError('Browser resource byte limit exceeded')
                reply.update(status=status, headers=headers, body_base64=base64.b64encode(body).decode())
                resources[-1].update(status='completed', http_status=status, finished_at=now())
            except Exception as exc:
                reply['error'] = str(exc)[:500]
                problems.append(reply['error'])
                resources[-1].update(status='failed', error=reply['error'], reason_code=reason_code, finished_at=now())
            stage = 'renderer_wait'
            progress()
            if reason_code == 'request_budget':
                raise ValueError('Browser resource request budget exhausted')
            process.stdin.write(json.dumps(reply) + '\n')
            process.stdin.flush()
        raise ValueError('Browser capture deadline exceeded')
    except Exception as exc:
        # A failed renderer can still have unreported queued requests.
        progress(complete=False)
        return {'error': str(exc)[:5000], 'fetch_receipts': fetcher.receipts, 'resource_receipts': resources,
                'accounting_complete': False,
                'stage': stage, 'renderer_stage': renderer_stage, 'browser_problems': browser_problems}
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdin.close()
        process.stdout.close()


def main():
    try:
        raw = sys.stdin.buffer.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Capture input exceeds limit')
        result = capture(json.loads(raw))
    except Exception as exc:
        result = {'error': str(exc)[:5000], 'provider': 'node-playwright-chromium'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
