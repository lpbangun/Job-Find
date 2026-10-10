"""Deployment-owned rendered open-path verification, separate from model output.

Public API accepts a Job, never an imported capture/JSON proof. A private child
process obtains observations using sandboxed Chromium and PublicFetcher. This
verifies that an application path is presented, not that submission would work.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import tempfile
import re
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit
from .identity import canonical_job_id
from .models import Evidence, now
from .routing import _run_host
from .transport import canonical_url
from .verification import POOLS, CLOSED, OTHER_INTENT, APPLICATION_INTENT, NAME_FIELDS, JOB_ID_FIELDS, _field_name


@dataclass(frozen=True)
class BrowserPolicy:
    allowed_hosts: tuple[str, ...]
    trusted_proxy_hosts: tuple[str, ...] = ()
    executable_path: str | None = None
    node_executable: str = 'node'
    playwright_module: str = 'playwright-core'
    timeout: float = 30
    max_parallel: int = 1
    request_budget: int = 40
    max_response_bytes: int = 3_000_000
    max_total_bytes: int = 12_000_000
    max_age_seconds: float = 300

    def __post_init__(self):
        for name in ('timeout', 'max_age_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid browser time limit')
        for name in ('max_parallel', 'request_budget', 'max_response_bytes', 'max_total_bytes'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError('Invalid browser resource limit')
        if not self.allowed_hosts or set(self.trusted_proxy_hosts) - set(self.allowed_hosts):
            raise ValueError('Explicit browser host allowlist required')
        for host in self.allowed_hosts:
            if not isinstance(host, str) or urlsplit(canonical_url('https://' + host + '/')).netloc != host:
                raise ValueError('Browser hosts must be exact canonical public hostnames')


def _target(job, policy):
    canonical = canonical_url(job.url)
    host = urlsplit(canonical).hostname
    if host not in policy.allowed_hosts or not job.title.strip():
        raise ValueError('Job is outside the configured browser source policy')
    if job.provider in ('lever', 'greenhouse'):
        if canonical_job_id(canonical) != job.identity:
            raise ValueError('ATS URL does not match exact posting identity')
        path = f'/{job.board}/{job.external_id}' if job.provider == 'lever' else f'/{job.board}/jobs/{job.external_id}'
        if canonical != canonical_url('https://' + host + path):
            raise ValueError('Unsupported ATS posting route or query')
        application = canonical + '/apply' if job.provider == 'lever' else canonical
        adapter = job.provider
    elif job.provider == 'structured':
        digest = hashlib.sha256(job.description.encode()).hexdigest()
        if not any(e.field == 'description' and canonical_url(e.url) == canonical and e.digest == digest for e in job.evidence):
            raise ValueError('Generic posting needs canonical source-bound description evidence')
        application, adapter = canonical, 'same-page-form'
    else:
        raise ValueError('No rendered adapter for this source type')
    return {'identity': job.identity, 'title': job.title, 'canonical_url': canonical,
            'application_url': application, 'adapter': adapter, 'external_id': job.external_id, 'company': job.company}


def _timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Capture timestamp must include timezone')
    return result


def _evaluate(capture, target, nonce, policy):
    """Private deterministic check of an internally produced worker result."""
    if capture.get('error'):
        raise ValueError(capture['error'])
    if (capture.get('nonce') != nonce or capture.get('provider') != 'node-playwright-chromium'
            or capture.get('source_kind') != 'live' or capture.get('target') != target
            or not capture.get('browser_version') or not capture.get('session_id')):
        raise ValueError('Untrusted, synthetic or mismatched browser capture')
    start, observed = _timestamp(capture['started_at']), _timestamp(capture['observed_at'])
    current = datetime.now(timezone.utc)
    if not start <= observed <= current or current - start > timedelta(seconds=policy.max_age_seconds):
        raise ValueError('Expired or future browser capture')
    raw = capture['rendered_html'].encode()
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != capture['rendered_sha256']:
        raise ValueError('Rendered document hash mismatch or byte limit exceeded')
    snap = capture['snapshot']
    if canonical_url(snap['url']) != target['application_url']:
        raise ValueError('Browser navigated away from the exact application target')
    if capture.get('accounting_complete') is not True:
        raise ValueError('Browser request accounting is incomplete')
    if capture['problems'] or snap['overflow']:
        raise ValueError('Incomplete browser capture or blocked resource')
    if not any(r.get('url') == target['application_url'] and r.get('status') == 200 and r.get('sha256')
               for r in capture['fetch_receipts']):
        raise ValueError('Official document request receipt is missing')
    return _classify_snapshot(snap, target)


def _classify_snapshot(snap, target):
    """Pure DOM classification; not an evidence-import or qualification API."""
    text = snap['text']
    if CLOSED.search(text):
        return 'closed', 'Official rendered closed notice'
    if snap['challenge'] or re.search(r'\b(?:verify you are human|checking your browser|access denied|just a moment)\b', text, re.I):
        raise ValueError('Access challenge prevents rendered verification')
    if target['title'].casefold() not in text.casefold():
        raise ValueError('Rendered posting title mismatch')
    if target['adapter'] == 'same-page-form':
        company = re.sub(r'[^a-z0-9]', '', target['company'].casefold())
        identity_text = re.sub(r'[^a-z0-9]', '', (snap.get('document_title', '') + ' ' + text).casefold())
        if not company or company == 'unknown' or company not in identity_text:
            raise ValueError('Rendered employer identity mismatch')
    if snap['unsupported_frames']:
        raise ValueError('Visible embedded frame requires another supported adapter')
    for form in snap['forms']:
        if not form['visible'] or form['overflow'] or OTHER_INTENT.search(form['context']):
            continue
        # No explicit action is required for an open path. A conflicting action
        # or hidden posting ID remains negative evidence, never ignored.
        controls = form['controls']
        ids = [c['value'] for c in controls if c['type'] == 'hidden' and _field_name(c['name']) in JOB_ID_FIELDS]
        if any(value and value != target['external_id'] for value in ids):
            continue
        def safe_action(action):
            if not action:
                return True
            from urllib.parse import urljoin
            resolved = canonical_url(urljoin(target['application_url'], action))
            return resolved in (target['application_url'], target['canonical_url'])
        try:
            if not safe_action(form['action']):
                continue
        except ValueError:
            continue
        usable = [c for c in controls if c['owned'] and c['visible'] and c['enabled']]
        names = [c for c in usable if c['tag'] == 'input' and c['type'] == 'text' and c['editable'] and _field_name(c['name']) in NAME_FIELDS]
        emails = [c for c in usable if c['tag'] == 'input' and c['editable'] and
                  (c['type'] == 'email' or (c['type'] == 'text' and _field_name(c['name']) in {'email', 'emailaddress', 'applicantemail', 'candidateemail'}))]
        if not names or not emails or any(not c['empty'] for c in names + emails):
            continue
        for button in usable:
            if not ((button['tag'] == 'button' and button['type'] in ('button', 'submit')) or
                    (button['tag'] == 'input' and button['type'] == 'submit')):
                continue
            if not APPLICATION_INTENT.search(button['label']) or OTHER_INTENT.search(button['label']):
                continue
            try:
                if safe_action(button['formaction']):
                    return 'open', 'Official job-bound rendered application path is visible and enabled'
            except ValueError:
                continue
    raise ValueError('No supported job-bound rendered application form established')


class BrowserApplicationVerifier:
    def __init__(self, policy):
        if type(policy) is not BrowserPolicy:
            raise TypeError('BrowserPolicy is deployment configuration')
        self.policy = policy
        self._slots = threading.BoundedSemaphore(policy.max_parallel)
        self.receipts = []
        self._lock = threading.Lock()

    def _capture(self, target, timeout, nonce, fixture_html=None):
        request = {'target': target, 'timeout': timeout, 'nonce': nonce, 'closed_pattern': CLOSED.pattern,
                   'allowed_hosts': self.policy.allowed_hosts,
                   'trusted_proxy_hosts': self.policy.trusted_proxy_hosts,
                   'executable_path': self.policy.executable_path,
                   'node_executable': self.policy.node_executable,
                   'playwright_module': self.policy.playwright_module,
                   'request_budget': self.policy.request_budget,
                   'max_response_bytes': self.policy.max_response_bytes,
                   'max_total_bytes': self.policy.max_total_bytes}
        if fixture_html is not None:
            request['fixture_html'] = fixture_html
        with tempfile.TemporaryDirectory(prefix='jobrouter-browser-') as directory:
            request['progress_path'] = str(Path(directory) / 'progress.json')
            try:
                result = _run_host([sys.executable, '-m', 'jobrouter.browser_capture'], json.dumps(request), timeout, 2_000_000)
            except Exception as exc:
                result = {'error': str(exc).replace('Host model', 'Browser capture'), 'accounting_complete': False}
            path = Path(request['progress_path'])
            if path.exists():
                with path.open('rb') as source:
                    raw = source.read(2_000_001)
                if len(raw) <= 2_000_000:
                    progress = json.loads(raw)
                    for key in ('fetch_receipts', 'resource_receipts', 'accounting_complete', 'stage', 'renderer_stage', 'browser_problems'):
                        result.setdefault(key, progress.get(key, [] if key.endswith('receipts') or key == 'browser_problems' else (False if key == 'accounting_complete' else 'unknown')))
            return result

    def verify(self, job):
        deadline = time.monotonic() + self.policy.timeout
        nonce = uuid.uuid4().hex
        receipt = {'capture_id': nonce, 'job_id': job.identity, 'started_at': now(),
                   'method': 'rendered_open_path', 'submission_tested': False,
                   'accounting_complete': True, 'fetch_receipts': [], 'resource_receipts': []}
        acquired = False
        try:
            if POOLS.search(job.title):
                job.availability = 'lead'
                receipt.update(status='lead', reason='Speculative pool is not a verified vacancy', checked_at=now())
                return receipt
            if job.deadline:
                expiry = datetime.fromisoformat(job.deadline.replace('Z', '+00:00'))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry < datetime.now(timezone.utc):
                    job.availability = 'closed'
                    receipt.update(status='closed', reason='Published deadline has passed', checked_at=now())
                    return receipt
            target = _target(job, self.policy)
            acquired = self._slots.acquire(timeout=max(0, deadline - time.monotonic()))
            if not acquired:
                raise ValueError('Browser concurrency wait exceeded deadline')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('Browser deadline exceeded')
            receipt['accounting_complete'] = False
            capture = self._capture(target, remaining, nonce)
            receipt.update(browser_problems=capture.get('browser_problems', []),
                           fetch_receipts=capture.get('fetch_receipts', []),
                           resource_receipts=capture.get('resource_receipts', []),
                           accounting_complete=capture.get('accounting_complete', False),
                           stage=capture.get('stage', 'unknown'), renderer_stage=capture.get('renderer_stage', 'unknown'))
            status, reason = _evaluate(capture, target, nonce, self.policy)
            if time.monotonic() >= deadline:
                raise ValueError('Browser deadline exceeded')
            receipt.update({'status': status, 'reason': reason, 'checked_at': capture['observed_at'],
                            'browser_version': capture['browser_version'], 'session_id': capture['session_id'], 'apply_url': target['application_url'],
                            'capture_sha256': hashlib.sha256(json.dumps(capture, sort_keys=True).encode()).hexdigest(),
                            'fetch_receipts': capture['fetch_receipts']})
            if status == 'open':
                # This record is generated only after our own browser worker and
                # deterministic checks. Model responses cannot enter this path.
                proof = json.dumps({'capture_id': nonce, 'capture_sha256': receipt['capture_sha256'],
                                    'method': 'rendered_open_path', 'submission_tested': False}, sort_keys=True)
                evidence = Evidence.from_text(target['application_url'], proof, proof,
                                              'rendered_application_form', capture['started_at'])
                evidence.expires_at = (_timestamp(capture['started_at']) + timedelta(seconds=self.policy.max_age_seconds)).isoformat()
                job.evidence.append(evidence)
                job.apply_url = target['application_url']
                job.observed_at = capture['observed_at']
            job.availability = status
        except Exception as exc:
            job.availability = 'unverified'
            receipt.update({'status': 'unverified', 'reason': str(exc)[:5000], 'checked_at': now()})
        finally:
            if acquired:
                self._slots.release()
            with self._lock:
                self.receipts.append(receipt)
        return receipt
