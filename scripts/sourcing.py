#!/usr/bin/env python3
"""Bounded, host-interpreted sourcing receipts. No provider or model dependency."""
import base64
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid
import selectors
import shlex
import signal
import subprocess
import http.client
import ipaddress
import socket
import ssl
import multiprocessing
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode


def canonical(url):
    parts = urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('only public HTTP(S) URLs without credentials are accepted')
    if any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('unsafe URL characters')
    port = parts.port
    if port and port not in (80, 443):
        raise ValueError('only HTTP(S) standard ports allowed')
    host = parts.hostname.lower().encode('idna').decode()
    netloc = '[' + host + ']' if ':' in host else host
    if port and port != (443 if parts.scheme.lower() == 'https' else 80):
        netloc += ':' + str(port)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or '/', urlencode(sorted(query)), ''))


def resolve_worker(pipe, host, port):
    try:
        pipe.send(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
    except Exception as exc:
        pipe.send(str(exc))
    finally:
        pipe.close()


def public_address(url, timeout):
    url = canonical(url)
    parts = urlsplit(url)
    host = parts.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError('non-public or reserved literal address denied')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('local hostname denied')
    parent, child = multiprocessing.Pipe(False)
    proc = multiprocessing.get_context('fork').Process(target=resolve_worker,
                 args=(child, host, parts.port or (443 if parts.scheme == 'https' else 80)))
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise ValueError('DNS timeout')
        addresses = parent.recv()
        if isinstance(addresses, str) or not addresses:
            raise ValueError('DNS resolution failed')
        ips = [a[4][0] for a in addresses]
        if any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('non-public or reserved address denied')
        return ips[0]
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join()
        parent.close()


def wire_request(url, timeout, cap, address):
    parts = urlsplit(url)
    deadline = time.monotonic() + timeout
    conn = http.client.HTTPConnection(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), timeout=timeout)
    # Pin the approved address: no second DNS lookup, TLS still authenticates the original hostname.
    sock = socket.create_connection((address, conn.port), timeout=timeout)
    try:
        if parts.scheme == 'https':
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        conn.sock = sock
        conn.request('GET', urlunsplit(('', '', parts.path or '/', parts.query, '')),
                     headers={'User-Agent': 'bounded-job-sourcing/0.1', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        headers = {k.lower(): v for k, v in response.getheaders()}
        data = bytearray()
        while len(data) <= cap:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ValueError('fetch timeout')
            sock.settimeout(left)
            chunk = response.read1(min(65536, cap + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        return response.status, headers, bytes(data), url
    finally:
        conn.close()
        sock.close()


def wire_worker(pipe, args):
    try:
        pipe.send(wire_request(*args))
    except Exception as exc:
        pipe.send(str(exc))
    finally:
        pipe.close()


def request(url, timeout, cap, address):
    parent, child = multiprocessing.Pipe(False)
    proc = multiprocessing.get_context('fork').Process(target=wire_worker, args=(child, (url, timeout, cap, address)))
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise ValueError('fetch hard timeout')
        output = parent.recv()
        if isinstance(output, str):
            raise ValueError(output)
        return output
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join()
        parent.close()


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.scripts = []
        self.script = None

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'script' and (dict(attrs).get('type') or '').lower() == 'application/ld+json':
            self.script = []
        if not self.skip:
            if tag == 'li':
                self.parts.append('\n- ')
            elif tag in ('p', 'div', 'section', 'article', 'br', 'hr', 'ul', 'ol', 'tr') or re.fullmatch('h[1-6]', tag):
                self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script))
            self.script = None
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag in ('li', 'p', 'div', 'section', 'article', 'ul', 'ol', 'tr') or re.fullmatch('h[1-6]', tag):
            self.parts.append('\n')

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if not self.skip:
            self.parts.append(data)


def html_text(content, fragment=False):
    if not isinstance(content, str):
        return ''
    # Only selected fragments may decode markup before parsing. Full pages
    # must retain original script/style boundaries; HTMLParser decodes text.
    # Bounded entity layers and block/list boundaries inspired by JobSSS
    # discovery.js (MIT, https://github.com/lpbangun/jobsss); stdlib adaptation.
    for _ in range(3 if fragment else 0):
        decoded = unescape(content)
        if decoded == content:
            break
        content = decoded
    parser = Text()
    parser.feed(content)
    return '\n'.join(line for line in (' '.join(p.split()) for p in ''.join(parser.parts).splitlines()) if line)


def extract_posting(content, url):
    parser = Text()
    parser.feed(content)
    postings = []
    metadata_incomplete = False
    visited = 0
    for script in parser.scripts:
        try:
            item = json.loads(script)
        except RecursionError:
            metadata_incomplete = True
            break
        except ValueError:
            continue
        stack = [(item, 0)]
        while stack:
            item, depth = stack.pop()
            visited += 1
            if depth > 64 or visited > 4096:
                metadata_incomplete = True
                break
            if isinstance(item, list):
                if len(item) + len(stack) + visited > 4096:
                    metadata_incomplete = True
                    break
                stack.extend((child, depth + 1) for child in reversed(item))
            elif isinstance(item, dict):
                types = item.get('@type', [])
                if types == 'JobPosting' or isinstance(types, list) and 'JobPosting' in types:
                    postings.append(item)
                elif '@graph' in item:
                    stack.append((item['@graph'], depth + 1))
        if metadata_incomplete:
            break
    # Incomplete traversal cannot establish uniqueness or safely infer identity.
    if metadata_incomplete:
        postings = []
    matches = []
    for item in postings:
        supplied = item.get('url')
        if supplied is not None:
            try:
                if isinstance(supplied, str) and supplied.strip() and canonical(urljoin(url, supplied)) == url:
                    matches.append(item)
            except ValueError:
                pass
    posting = matches[0] if len(matches) == 1 else None
    binding = 'explicit_url'
    if not matches and len(postings) == 1 and postings[0].get('url') is None:
        posting = postings[0]
        binding = 'page_url_inferred'
    if posting is None:
        text = html_text(content)
        page_title = re.search(r'<title\b[^>]*>(.*?)</title\s*>', content, re.I | re.S)
        identity = re.fullmatch(r'Job Application for (.+) at (.+)', html_text(page_title[1]) if page_title else '')
        # Never infer named identity from a page containing rejected/ambiguous metadata.
        if identity and not postings and not metadata_incomplete:
            return text, {'title': identity[1], 'company': identity[2], 'description': text,
                          'source': 'visible HTML', 'binding': 'visible_page_title', 'url': url,
                          'caveat': 'Page-title identity requires host verification.'}
        return text, None
    title = html_text(posting.get('title', ''), fragment=True)
    organization = posting.get('hiringOrganization')
    company = html_text(organization.get('name', ''), fragment=True) if isinstance(organization, dict) else ''
    description = html_text(posting.get('description', ''), fragment=True)
    if not title or not company:
        return html_text(content), None
    metadata = {'title': title, 'company': company, 'description': description,
                'source': 'JobPosting JSON-LD', 'binding': binding, 'url': url,
                'caveat': 'Metadata identity is not employer authority or current acceptance proof.'}
    return '\n'.join(filter(None, (title, company, description))), metadata


def fetch(path, url, transport=None):
    receipt, timeout, cap = reserve(path, 'fetch', url)
    root = receipt
    deadline = time.monotonic() + timeout
    try:
        for hop in range(6):
            if hop:
                receipt, left, cap = reserve(path, 'fetch', url)
                deadline = min(deadline, time.monotonic() + left)
            address = public_address(url, max(0.001, deadline - time.monotonic()))
            url = canonical(url)
            left = deadline - time.monotonic()
            if left <= 0:
                raise ValueError('fetch timeout')
            status, headers, data, final = (transport(url, left, cap) if transport else request(url, left, cap, address))
            if canonical(final) != url:
                raise ValueError('transport followed unaccounted redirect')
            if 'content-length' in headers and int(headers['content-length']) != len(data) and status == 200:
                raise ValueError('incomplete response body')
            if len(data) > cap or headers.get('content-encoding', 'identity') != 'identity':
                raise ValueError('oversized or encoded response')
            receipt.update(url=url, http_status=status, headers=headers)
            if status in (301, 302, 303, 307, 308):
                receipt.update(status='redirect', redirect_to=urljoin(url, headers.get('location', '')))
                finish(path, 'fetch', receipt)
                url = receipt['redirect_to']
                continue
            if status != 200:
                raise ValueError('HTTP status ' + str(status))
            content = data.decode('utf-8', errors='replace')
            if 'json' in headers.get('content-type', ''):
                text = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
            else:
                text, posting = extract_posting(content, url)
                if posting:
                    receipt['posting'] = posting
            receipt.update(status='ok', text=text, raw_body=content, raw_base64=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest(),
                           text_sha256=hashlib.sha256(text.encode()).hexdigest(), bytes=len(data),
                           requested_url=root['target'])
            return finish(path, 'fetch', receipt)
        raise ValueError('redirect limit exhausted')
    except Exception as exc:
        # A consumed attempt survives even if a later redirect cannot reserve another request.
        receipt = dict(receipt)
        receipt.update(status='error', error=str(exc), requested_url=root['target'])
        return finish(path, 'fetch', receipt)


def reserve(path, kind, target):
    with locked(path) as state:
        limits = state['brief']['limits']
        remaining = state['created_at'] + limits['seconds'] - now()
        if remaining <= 0 or state['used_requests'] >= limits['requests']:
            raise ValueError('run deadline or request budget exhausted')
        rid = uuid.uuid4().hex
        state['used_requests'] += 1
        receipt = {'id': rid, 'run_id': state['run_id'], 'started_at': now(),
                   'status': 'pending', 'target': target}
        state['searches' if kind == 'search' else 'evidence'][rid] = receipt
        event(state, 'request_reserved', id=rid, operation=kind, target=target)
        return receipt, min(limits['timeout'], remaining), limits['max_bytes']


def finish(path, kind, receipt):
    receipt['captured_at'] = now()
    with locked(path) as state:
        state['searches' if kind == 'search' else 'evidence'][receipt['id']] = receipt
        posting = receipt.get('posting')
        if kind == 'fetch' and receipt['status'] == 'ok' and posting:
            existing = next((c for c in state['candidates'].values() if c['url'] == receipt['url']), None)
            # Receipt and candidate share one fsynced transaction. Never replace
            # host judgments or refresh their evidence/availability implicitly.
            if existing is None:
                cid = uuid.uuid4().hex
                candidate = {'id': cid, 'url': receipt['url'], 'company': posting['company'],
                             'title': posting['title'], 'kind': 'vacancy', 'provisional': True,
                             'availability': 'unverifiable', 'availability_evidence': [],
                             'evidence_refs': [receipt['id']],
                             'identity': {key: {'ref': receipt['id'], 'passage': posting[key]}
                                          for key in ('company', 'title')},
                             'hard_findings': [{'id': c['id'], 'status': 'unknown'}
                                               for c in state['brief']['hard_constraints']],
                             'fit_dimensions': [], 'submitted_at': receipt['captured_at'],
                             'intake': {'source': posting['source'], 'binding': posting['binding'],
                                        'caveat': posting['caveat']}}
                state['candidates'][cid] = candidate
                event(state, 'candidate_checkpointed', id=cid, ref=receipt['id'])
            receipt['candidate_id'] = existing['id'] if existing else cid
        event(state, 'request_finished', id=receipt['id'], status=receipt['status'])
    return receipt


def bridge(command, payload, timeout, max_bytes):
    proc = subprocess.Popen(shlex.split(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + timeout
    try:
        assert proc.stdin is not None and proc.stdout is not None
        pending = memoryview(json.dumps(payload).encode())
        os.set_blocking(proc.stdin.fileno(), False)
        data = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise ValueError('search bridge timeout')
                for key, _ in selector.select(left):
                    if key.fileobj is proc.stdin:
                        sent = os.write(key.fd, pending[:4096])
                        pending = pending[sent:]
                        if not pending:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                        continue
                    chunk = os.read(key.fd, min(65536, max_bytes + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError('search bridge output exceeds max_bytes')
        if proc.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise ValueError('search bridge nonzero exit')
        return json.loads(data)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()
        proc.stdin.close()


def search(path, query, limit=5):
    if not isinstance(query, str) or not query.strip() or len(query) > 4096:
        raise ValueError('query must be nonempty and at most 4096 characters')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    receipt, timeout, max_bytes = reserve(path, 'search', query)
    receipt.update(query=query, limit=limit, results=[])
    try:
        command = os.environ.get('SOURCING_SEARCH_COMMAND')
        if not command:
            raise ValueError('SOURCING_SEARCH_COMMAND unavailable')
        output = bridge(command, {'query': query, 'limit': limit}, timeout, max_bytes)
        if not isinstance(output.get('results'), list) or not isinstance(output.get('backend'), str):
            raise ValueError('bridge requires results list and backend string')
        if len(output['results']) > limit:
            raise ValueError('bridge exceeded requested limit')
        for item in output['results']:
            if not all(isinstance(item.get(k), str) for k in ('url', 'title', 'description')):
                raise ValueError('invalid result fields')
        receipt.update(status='ok', results=output['results'], backend=output['backend'])
    except Exception as exc:
        receipt.update(status='error', error=str(exc))
    return finish(path, 'search', receipt)


def now():
    return time.time()


def dump(path, value):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as out:
        json.dump(value, out, indent=2, allow_nan=False)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def locked(path):
    path = Path(path)
    with (path / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads((path / 'state.json').read_text())
        yield state
        dump(path / 'state.json', state)


def event(store, kind, **data):
    store['events'].append({'at': now(), 'kind': kind, **data})


def initialize(path, brief):
    if brief.get('mode') not in ('prompt_only', 'profile', 'resume'):
        raise ValueError('mode must be prompt_only, profile, or resume')
    if not isinstance(brief.get('preferences'), list) or not isinstance(brief.get('hard_constraints'), list):
        raise ValueError('preferences and hard_constraints must be lists')
    if type(brief.get('requested_count')) is not int or brief['requested_count'] < 1:
        raise ValueError('requested_count must be a positive integer')
    if any(type(c.get('mandatory', True)) is not bool or not isinstance(c.get('description', ''), str) for c in brief['hard_constraints']):
        raise ValueError('constraint mandatory must be boolean and description must be text')
    ids = [c['id'] for c in brief['hard_constraints']]
    if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError('unique nonempty constraint ids required')
    limits = brief['limits']
    for key in ('requests', 'seconds', 'timeout', 'max_bytes', 'freshness_seconds'):
        value = limits[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('limits must be finite and positive: ' + key)
    if type(limits['requests']) is not int or type(limits['max_bytes']) is not int:
        raise ValueError('requests and max_bytes must be integers')
    path = Path(path)
    history = brief.get('application_history', [])
    if brief.get('application_history_file'):
        file = Path(brief['application_history_file'])
        history = json.loads((file if file.is_absolute() else path / file).read_text())
    if not isinstance(history, list) or any(not isinstance(h, dict) for h in history):
        raise ValueError('application history must be a JSON array of records')
    history = [{**h, 'url': canonical(h['url']) if h.get('url') else None} for h in history]
    path.mkdir(parents=True, exist_ok=True)
    with (path / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (path / 'state.json').exists():
            raise ValueError('run exists; resume it, do not reset its budget')
        state = {'version': 1, 'run_id': uuid.uuid4().hex, 'brief': brief,
                 'created_at': now(), 'used_requests': 0, 'events': [],
                 'actions': {}, 'evidence': {}, 'searches': {}, 'candidates': {},
                 'application_history': history,
                 'history_provided': bool('application_history' in brief or brief.get('application_history_file'))}
        event(state, 'init')
        dump(path / 'state.json', state)
    return state


def snapshot(path):
    with locked(path) as state:
        return state


def action(path, payload):
    with locked(path) as state:
        aid = payload.get('id') or uuid.uuid4().hex
        old = state['actions'].get(aid, {})
        item = {**old, **payload, 'id': aid, 'updated_at': now()}
        for key in ('target', 'pathway', 'reason'):
            if not item.get(key):
                raise ValueError('action requires ' + key)
        item.setdefault('parent', None)
        item.setdefault('state', 'pending')
        if item['state'] not in ('pending', 'active', 'done', 'blocked', 'exhausted'):
            raise ValueError('invalid action state')
        if item['parent'] and item['parent'] not in state['actions']:
            raise ValueError('unknown action parent')
        state['actions'][aid] = item
        event(state, 'action', id=aid, state=item['state'])
        return item


def scrub(value):
    # Keep malformed scores inspectable without writing nonstandard JSON NaN/Infinity.
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def submit(path, candidate):
    candidate = scrub(candidate)
    if not isinstance(candidate, dict):
        raise ValueError('candidate must be an object')
    url = canonical(candidate['url'])
    with locked(path) as state:
        existing = next((c for c in state['candidates'].values() if c['url'] == url or
                        (candidate.get('posting_id') and candidate.get('posting_provider') and
                         c.get('posting_id') == candidate['posting_id'] and
                         c.get('posting_provider') == candidate['posting_provider'] and
                         c.get('company') == candidate.get('company'))), None)
        cid = existing['id'] if existing else uuid.uuid4().hex
        item = {**candidate, 'id': cid, 'url': url, 'submitted_at': now()}
        state['candidates'][cid] = item
        event(state, 'candidate_submitted', id=cid, replaced=bool(existing))
        return item


def posting_scope(value, candidate):
    if isinstance(value, dict):
        ids = [value.get(k) for k in ('id', 'jobId', 'postingId')]
        urls = [value.get(k) for k in ('url', 'jobUrl', 'canonicalUrl')]
        if candidate.get('posting_id') and candidate['posting_id'] in ids and candidate['url'] in urls:
            return json.dumps(value, ensure_ascii=False, indent=2)
        for child in value.values():
            found = posting_scope(child, candidate)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = posting_scope(child, candidate)
            if found is not None:
                return found
    return None


def validate(state, candidate):
    issues = []
    refs = candidate.get('evidence_refs', [])
    current = now()
    def quote(q, identity=False, check_only=False):
        if not isinstance(q, dict) or q.get('ref') not in refs:
            raise ValueError('quote reference must be in evidence_refs')
        e = state['evidence'].get(q['ref'])
        if not e or e.get('run_id') != state['run_id'] or e.get('status') != 'ok' or e.get('http_status') != 200:
            raise ValueError('missing, foreign, failed, or incomplete receipt')
        at = e.get('captured_at')
        if type(at) not in (int, float) or not math.isfinite(at) or at > current or at < state['created_at'] or current - at > state['brief']['limits']['freshness_seconds']:
            raise ValueError('future, stale, or invalid capture timestamp')
        text = e.get('text', '')
        if hashlib.sha256(text.encode()).hexdigest() != e.get('text_sha256'):
            raise ValueError('evidence text hash mismatch')
        canonical(e['url'])
        host = urlsplit(e['url']).hostname
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if (address is not None and not address.is_global) or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError('unsafe receipt URL')
        raw = base64.b64decode(e.get('raw_base64', ''), validate=True)
        if hashlib.sha256(raw).hexdigest() != e.get('sha256') or raw.decode('utf-8', errors='replace') != e.get('raw_body'):
            raise ValueError('raw evidence hash mismatch')
        if q.get('representation') == 'raw':
            text = e['raw_body']
        if not check_only and canonical(e['url']) != candidate['url']:
            linked = False
            for link in candidate.get('source_links', []):
                source = state['evidence'].get(link.get('ref'), {})
                if source.get('url') == candidate['url'] and e['url'] in quote(link, identity=True):
                    linked = True
            if not linked:
                raise ValueError('source receipt is not explicitly linked by canonical evidence')
            scope = posting_scope(json.loads(e['raw_body']), candidate)
            if scope is None:
                raise ValueError('source JSON does not bind exact posting id and canonical URL')
            text = scope
        passage = q.get('passage')
        if not isinstance(passage, str) or not passage.strip() or passage not in text:
            raise ValueError('supporting passage absent from captured text or bound posting scope')
        return passage
    hard = []
    score = None
    try:
        for key in ('company', 'title'):
            if not isinstance(candidate.get(key), str) or not candidate[key].strip():
                raise ValueError('company and title required')
        kind = candidate.get('kind')
        if kind not in ('vacancy', 'invitation', 'lead'):
            raise ValueError('kind must be vacancy, invitation, or lead')
        if not isinstance(refs, list) or not refs:
            raise ValueError('captured evidence_refs required')
        for ref in refs:
            e = state['evidence'].get(ref)
            quote({'ref': ref, 'passage': (e or {}).get('text', '')}, check_only=True)
        identity = candidate.get('identity', {})
        for key in ('company', 'title'):
            passage = quote(identity.get(key), identity=True)
            if candidate[key].casefold() not in passage.casefold():
                raise ValueError('identity passage does not contain ' + key)
        availability = candidate.get('availability')
        if availability not in ('open', 'closed', 'unverifiable'):
            raise ValueError('invalid availability')
        if availability in ('open', 'closed'):
            support = candidate.get('availability_evidence', [])
            if not support:
                raise ValueError('explicit availability supporting passages required')
            for q in support:
                quote(q, identity=True)
        findings = candidate.get('hard_findings', [])
        known_ids = {c['id'] for c in state['brief']['hard_constraints']}
        if any(f.get('id') not in known_ids for f in findings) or len({f.get('id') for f in findings}) != len(findings):
            raise ValueError('unknown or duplicate hard finding id')
        for constraint in state['brief']['hard_constraints']:
            f = next((f for f in findings if f.get('id') == constraint['id']), {'id': constraint['id'], 'status': 'unknown'})
            if f.get('status') not in ('pass', 'fail', 'unknown'):
                raise ValueError('invalid hard finding status')
            if f['status'] != 'unknown':
                quote(f)
            hard.append({**f, 'mandatory': constraint.get('mandatory', True)})
        dimensions = candidate.get('fit_dimensions', [])
        if kind == 'vacancy' and availability == 'open' and not any(f['mandatory'] and f['status'] == 'fail' for f in hard):
            if not dimensions:
                raise ValueError('fit dimensions missing')
            criteria = '\n'.join([str(p) for p in state['brief']['preferences']] + [c.get('description', '') for c in state['brief']['hard_constraints']])
            for d in dimensions:
                value = d.get('score')
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                    raise ValueError('fit scores must be finite numbers in 0..100')
                if not d.get('name'):
                    raise ValueError('fit dimension name required')
                quote(d.get('job'))
                if state['brief']['mode'] == 'prompt_only':
                    proof, source = d.get('criterion_passage'), criteria
                    if d.get('profile_passage'):
                        raise ValueError('prompt-only cannot assert resume proof')
                else:
                    proof, source = d.get('profile_passage'), state['brief'].get('profile_text', '')
                if not isinstance(proof, str) or not proof.strip() or proof not in source:
                    raise ValueError('profile/criteria proof missing from immutable brief')
            score = sum(d['score'] for d in dimensions) / len(dimensions)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        issues.append(str(exc))
    if issues or candidate.get('availability') == 'unverifiable':
        group, reason = 'unverifiable', issues or ['availability unverifiable']
    elif candidate['kind'] != 'vacancy':
        group, reason = 'leads', ['not a specific validated vacancy']
    elif candidate['availability'] == 'closed' or any(f['status'] == 'fail' and f['mandatory'] for f in hard):
        group, reason = 'excluded', ['closed or explicit mandatory constraint failure']
    elif any(f['status'] == 'unknown' and f['mandatory'] for f in hard):
        group, reason = 'conditional', ['mandatory constraints unresolved']
    else:
        group, reason = 'qualified', ['host-interpreted passages pass structural gates']
    history = state.get('application_history', [])
    exact = any(h.get('url') == candidate['url'] for h in history)
    collision = any(str(h.get('company', '')).strip().casefold() == str(candidate.get('company', '')).strip().casefold() and
                    str(h.get('title', '')).strip().casefold() == str(candidate.get('title', '')).strip().casefold() for h in history)
    history_status = ('exact_url_match' if exact else 'needs_review' if collision else
                      'not_found_in_available_records' if state.get('history_provided') else 'history_unavailable')
    if state['brief'].get('exclude_history_matches') and group == 'qualified':
        if exact:
            group, reason = 'excluded', ['exact canonical URL found in available application records']
        elif collision or not state.get('history_provided'):
            group, reason = 'conditional', ['application-history identity needs review or records unavailable']
    return {**candidate, 'group': group, 'reasons': reason, 'score': score, 'history_status': history_status,
            'validated_at': current, 'hard_findings': hard}


def results(path):
    with locked(path) as state:
        output = {g: [] for g in ('qualified', 'conditional', 'unverifiable', 'excluded', 'leads')}
        for candidate in state['candidates'].values():
            item = validate(state, candidate)
            output[item['group']].append(item)
        for items in output.values():
            items.sort(key=lambda c: (-(c['score'] if c['score'] is not None else -1), c['id']))
        output.update(version=1, run_id=state['run_id'], requested_count=state['brief']['requested_count'],
                      used_requests=state['used_requests'], limits=state['brief']['limits'],
                      counts={g: len(items) for g, items in output.items()},
                      shortlist=output['qualified'][:state['brief']['requested_count']],
                      caveat='Core checks receipts and quote presence, not semantic truth. Scores are rubric grades, not probabilities.')
        event(state, 'validated', counts=output['counts'])
        return output


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'status', 'action', 'search', 'fetch', 'submit', 'validate', 'results'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', required=True, help='durable run directory')
        cmd.add_argument('--out', help='explicit JSON output file, also printed on stdout')
        cmd.add_argument('--compact', action='store_true', help='omit raw/base64 and duplicate posting description from output only')
        if name == 'init':
            cmd.add_argument('--brief', required=True, help='JSON brief file')
            cmd.add_argument('--requests', type=int, help='override brief request limit before freezing run')
            cmd.add_argument('--seconds', type=float, help='override brief duration before freezing run')
        if name in ('action', 'submit'):
            cmd.add_argument('--file', required=True, help='JSON object file; - reads stdin')
        if name == 'search':
            cmd.add_argument('--query', required=True)
            cmd.add_argument('--limit', type=int, default=5)
        if name == 'fetch':
            cmd.add_argument('--url', required=True)
    args = parser.parse_args(argv)
    try:
        import sys
        if args.command in ('init', 'action', 'submit'):
            file = args.brief if args.command == 'init' else args.file
            payload = json.loads(sys.stdin.read() if file == '-' else Path(file).read_text())
            if args.command == 'init':
                for key in ('requests', 'seconds'):
                    if getattr(args, key) is not None:
                        payload['limits'][key] = getattr(args, key)
            output = {'init': initialize, 'action': action, 'submit': submit}[args.command](args.run, payload)
        elif args.command == 'search':
            output = search(args.run, args.query, args.limit)
        elif args.command == 'fetch':
            output = fetch(args.run, args.url)
        else:
            output = snapshot(args.run) if args.command == 'status' else results(args.run)
        if args.compact:
            def compact(value):
                if isinstance(value, dict):
                    return {k: compact(v) for k, v in value.items() if k not in ('raw_body', 'raw_base64')
                            and not (k == 'description' and 'binding' in value)}
                if isinstance(value, list):
                    return [compact(v) for v in value]
                return value
            output = compact(output)
        if args.out:
            out = Path(args.out)
            if out.resolve() in ((Path(args.run)/'state.json').resolve(), (Path(args.run)/'.lock').resolve()):
                raise ValueError('output cannot overwrite authoritative run files')
            out.parent.mkdir(parents=True, exist_ok=True)
            dump(out, output)
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
