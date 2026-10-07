import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sourcing', ROOT / 'scripts/sourcing.py')
s = importlib.util.module_from_spec(SPEC) if SPEC else None
if SPEC and SPEC.loader and (ROOT / 'scripts/sourcing.py').exists():
    SPEC.loader.exec_module(s)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        if hasattr(s, 'socket'):
            from unittest.mock import patch
            dns = patch.object(s.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
            dns.start()
            self.addCleanup(dns.stop)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'run'
        self.brief = {'mode': 'prompt_only', 'requested_count': 5,
                      'hard_constraints': [{'id': 'geo', 'description': 'Singapore', 'mandatory': True}],
                      'preferences': ['big tech'],
                      'limits': {'requests': 5, 'seconds': 60, 'timeout': 2,
                                 'max_bytes': 4096, 'freshness_seconds': 3600}}

    def init(self):
        self.assertTrue(hasattr(s, 'initialize'), 'runtime initialize is not implemented')
        return s.initialize(self.path, self.brief)

    def test_durable_init_and_action_resume(self):
        self.init()
        a = s.action(self.path, {'target': 'employer careers', 'pathway': 'A', 'reason': 'role discovery'})
        s.action(self.path, {'id': a['id'], 'state': 'blocked', 'reason': 'permission missing'})
        state = s.snapshot(self.path)
        self.assertEqual(state['actions'][a['id']]['state'], 'blocked')
        self.assertEqual(state['brief'], self.brief)
        self.assertEqual(state['used_requests'], 0)
        with self.assertRaises(ValueError):
            s.initialize(self.path, self.brief)

    def test_search_attempts_failures_and_resume_share_budget(self):
        self.init()
        self.assertTrue(hasattr(s, 'search'), 'search not implemented')
        from unittest.mock import patch
        with patch.dict(os.environ, {'SOURCING_SEARCH_COMMAND': ''}):
            for _ in range(5):
                receipt = s.search(self.path, 'Singapore engineer', 3)
                self.assertEqual(receipt['status'], 'error')
            with self.assertRaises(ValueError):
                s.search(self.path, 'retry', 3)
        state = s.snapshot(self.path)
        self.assertEqual(state['used_requests'], 5)
        self.assertEqual(len(state['searches']), 5)

    def test_parallel_reservation_is_atomic(self):
        self.brief['limits']['requests'] = 1
        self.init()
        self.assertTrue(hasattr(s, 'reserve'), 'reservation not implemented')
        from concurrent.futures import ThreadPoolExecutor
        def attempt(_):
            try:
                s.reserve(self.path, 'search', 'q')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)
        self.assertEqual(s.snapshot(self.path)['used_requests'], 1)

    def test_search_bridge_json_contract_and_timeout(self):
        import sys
        import shlex
        from unittest.mock import patch
        self.init()
        self.assertTrue(hasattr(s, 'search'), 'search not implemented')
        bridge = Path(self.tmp.name) / 'bridge.py'
        bridge.write_text('import json,sys\np=json.load(sys.stdin)\nprint(json.dumps({"backend":"fixture","results":[{"url":"https://example.com/job/1","title":p["query"],"description":"snippet"}]}))\n')
        command = shlex.join([sys.executable, str(bridge)])
        with patch.dict(os.environ, {'SOURCING_SEARCH_COMMAND': command}):
            r = s.search(self.path, 'engineer', 2)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['backend'], 'fixture')
        self.assertEqual(r['results'][0]['title'], 'engineer')
        bridge.write_text('import time\ntime.sleep(5)\n')
        with patch.dict(os.environ, {'SOURCING_SEARCH_COMMAND': command}):
            self.assertEqual(s.search(self.path, 'timeout', 2)['status'], 'error')

    def test_public_fetch_html_json_hash_and_failure_receipts(self):
        self.init()
        self.assertTrue(hasattr(s, 'fetch'), 'fetch not implemented')
        def transport(url, timeout, cap):
            return 200, {'content-type': 'text/html'}, b'<h1>Engineer</h1><p>Apply now Singapore</p>', url
        receipt = s.fetch(self.path, 'https://example.com/jobs/1', transport=transport)
        self.assertEqual(receipt['status'], 'ok')
        self.assertIn('Apply now Singapore', receipt['text'])
        self.assertEqual(len(receipt['sha256']), 64)
        receipt = s.fetch(self.path, 'https://example.com/jobs/2', transport=lambda *a: (200, {'content-type': 'application/json'}, b'{"title":"Engineer"}', a[0]))
        self.assertIn('Engineer', receipt['text'])
        receipt = s.fetch(self.path, 'https://example.com/jobs/3', transport=lambda *a: (404, {}, b'not found', a[0]))
        self.assertEqual(receipt['status'], 'error')
        self.assertNotIn('availability', receipt)

    def test_ssrf_denied_before_transport_and_redirect_rechecked(self):
        self.init()
        self.assertTrue(hasattr(s, 'fetch'), 'fetch not implemented')
        from unittest.mock import patch
        calls = []
        def forbidden(*a):
            calls.append(a[0])
            raise AssertionError('unsafe address reached transport')
        for url in ('file:///etc/passwd', 'http://127.0.0.1/x', 'http://[::1]/x', 'http://user:pass@example.com/x'):
            self.assertEqual(s.fetch(self.path, url, transport=forbidden)['status'], 'error')
        with patch.object(s.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('10.1.2.3', 80))]):
            self.assertEqual(s.fetch(self.path, 'https://evil.example/x', transport=forbidden)['status'], 'error')
        self.assertEqual(calls, [], 'SSRF-denied targets must never reach transport')
        self.brief['limits']['requests'] = 10
        other = Path(self.tmp.name) / 'redirect'
        s.initialize(other, self.brief)
        calls = []
        def redirect(url, *args):
            calls.append(url)
            return 302, {'location': 'http://127.0.0.1/private'}, b'', url
        r = s.fetch(other, 'https://example.com/job', transport=redirect)
        self.assertEqual(r['status'], 'error')
        self.assertEqual(len(calls), 1)
        self.assertEqual(s.snapshot(other)['used_requests'], 2)

    def test_fetch_byte_limit_and_redirect_budget(self):
        self.init()
        self.assertTrue(hasattr(s, 'fetch'), 'fetch not implemented')
        r = s.fetch(self.path, 'https://example.com/job', transport=lambda *a: (200, {}, b'x'*5000, a[0]))
        self.assertEqual(r['status'], 'error')
        calls = []
        def redirects(url, *a):
            calls.append(url)
            return 302, {'location': url + 'x'}, b'', url
        r = s.fetch(self.path, 'https://example.com/job', transport=redirects)
        self.assertEqual(r['status'], 'error')
        self.assertEqual(s.snapshot(self.path)['used_requests'], 5)
        self.assertEqual(len(calls), 4)

    def candidate(self, text='Acme Engineer Apply now Singapore big tech'):
        receipt = s.fetch(self.path, 'https://example.com/job/1', transport=lambda *a: (200, {}, text.encode(), a[0]))
        def quote(passage):
            return {'ref': receipt['id'], 'passage': passage}
        return {'company': 'Acme', 'title': 'Engineer', 'url': receipt['url'], 'kind': 'vacancy',
                'availability': 'open', 'evidence_refs': [receipt['id']],
                'identity': {'company': quote('Acme'), 'title': quote('Engineer')},
                'availability_evidence': [quote('Apply now')],
                'hard_findings': [{'id': 'geo', 'status': 'pass', **quote('Singapore')}],
                'fit_dimensions': [{'name': 'preference', 'score': 80, 'criterion_passage': 'big tech', 'job': quote('big tech')}]}

    def test_candidate_validation_ranking_quotes_unknowns_and_failures(self):
        self.init()
        self.assertTrue(hasattr(s, 'submit'), 'candidate submit not implemented')
        c = self.candidate()
        submitted = s.submit(self.path, c)
        result = s.results(self.path)
        self.assertEqual(result['qualified'][0]['id'], submitted['id'])
        self.assertEqual(result['qualified'][0]['score'], 80)
        c['hard_findings'] = []
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['conditional']), 1)
        c['hard_findings'] = [{'id': 'geo', 'status': 'fail', **c['identity']['title']}]
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['excluded']), 1)
        c['hard_findings'] = [{'id': 'geo', 'status': 'pass', 'ref': c['evidence_refs'][0], 'passage': 'invented quote'}]
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)

    def test_availability_not_http_success_redirect_or_notfound_alone(self):
        self.init()
        self.assertTrue(hasattr(s, 'submit'), 'candidate submit not implemented')
        c = self.candidate('Acme Engineer Singapore big tech Page not found')
        c['availability_evidence'] = []
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)
        c['availability_evidence'] = [c['identity']['title']]
        c['url'] = 'https://example.com/careers'
        bad_redirect = s.submit(self.path, c)
        self.assertTrue(any(item['id'] == bad_redirect['id'] for item in s.results(self.path)['unverifiable']))
        c['availability'] = 'closed'
        c['url'] = 'https://example.com/job/1'
        c['availability_evidence'] = []
        closed = s.submit(self.path, c)
        self.assertTrue(any(item['id'] == closed['id'] for item in s.results(self.path)['unverifiable']))

    def test_leads_nonfinite_and_missing_scores_are_separate(self):
        self.init()
        self.assertTrue(hasattr(s, 'submit'), 'candidate submit not implemented')
        c = self.candidate()
        c['kind'] = 'invitation'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['leads']), 1)
        c['kind'] = 'vacancy'
        for dimensions in ([], [{'name': 'x', 'job': c['identity']['title']}], [{'score': float('nan')}], [{'score': float('inf')}]):
            c['fit_dimensions'] = dimensions
            s.submit(self.path, c)
            self.assertEqual(len(s.results(self.path)['unverifiable']), 1)

    def test_receipts_future_stale_other_run_hash_and_profile_proof(self):
        self.brief['mode'] = 'resume'
        self.brief['profile_text'] = 'Built Python services'
        self.init()
        self.assertTrue(hasattr(s, 'submit'), 'candidate submit not implemented')
        c = self.candidate()
        c['fit_dimensions'][0].pop('criterion_passage')
        c['fit_dimensions'][0]['profile_passage'] = 'Built Python services'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['qualified']), 1)
        c['fit_dimensions'][0]['profile_passage'] = 'Invented years'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)
        c['fit_dimensions'][0]['profile_passage'] = 'Built Python services'
        for key, value in [('captured_at', s.now()+100), ('captured_at', s.now()-5000), ('run_id', 'foreign'), ('text_sha256', 'bad')]:
            with s.locked(self.path) as state:
                receipt = state['evidence'][c['evidence_refs'][0]]
                original = receipt[key]
                receipt[key] = value
            s.submit(self.path, c)
            self.assertEqual(len(s.results(self.path)['unverifiable']), 1)
            with s.locked(self.path) as state:
                state['evidence'][c['evidence_refs'][0]][key] = original
        c['evidence_refs'] = ['outside-run']
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)

    def test_history_exact_urls_and_title_company_collision(self):
        history = Path(self.tmp.name) / 'history.json'
        history.write_text(json.dumps([{'url': 'https://EXAMPLE.com/job/1?utm_source=old', 'company': 'Acme', 'title': 'Engineer'}]))
        self.brief['application_history_file'] = str(history)
        self.brief['exclude_history_matches'] = True
        self.init()
        c = self.candidate()
        s.submit(self.path, c)
        result = s.results(self.path)
        self.assertEqual(len(result['excluded']), 1)
        self.assertEqual(result['excluded'][0]['history_status'], 'exact_url_match')
        c2 = self.candidate()
        receipt = s.fetch(self.path, 'https://example.com/job/2', transport=lambda *a: (200, {}, b'Acme Engineer Apply now Singapore big tech', a[0]))
        c2['url'] = receipt['url']
        c2['evidence_refs'] = [receipt['id']]
        for q in [*c2['identity'].values(), *c2['availability_evidence'], *c2['hard_findings'], c2['fit_dimensions'][0]['job']]:
            q['ref'] = receipt['id']
        s.submit(self.path, c2)
        result = s.results(self.path)
        self.assertEqual(result['conditional'][0]['history_status'], 'needs_review')

    def test_dedupe_urls_without_fuzzy_role_merging(self):
        self.init()
        c = self.candidate()
        first = s.submit(self.path, c)
        c['url'] += '?utm_source=test#apply'
        self.assertEqual(s.submit(self.path, c)['id'], first['id'])
        c['url'] = 'https://example.com/job/2'
        second = s.submit(self.path, c)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(s.snapshot(self.path)['candidates']), 2)
        c['posting_id'], c['posting_provider'] = '123', 'example-acme'
        s.submit(self.path, c)
        c['url'] = 'https://example.com/job/alias'
        self.assertEqual(s.submit(self.path, c)['id'], second['id'])

    def test_deadline_pending_resume_and_unsafe_receipt(self):
        self.init()
        c = self.candidate()
        with s.locked(self.path) as state:
            state['evidence'][c['evidence_refs'][0]]['url'] = 'http://127.0.0.1/job'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)
        with s.locked(self.path) as state:
            state['created_at'] -= 100
        with self.assertRaises(ValueError):
            s.search(self.path, 'late', 1)

    def test_cli_init_status_submit_validate_results_and_error_exit(self):
        import subprocess
        import sys
        brief = Path(self.tmp.name) / 'brief.json'
        brief.write_text(json.dumps(self.brief))
        def cli(*args):
            p = subprocess.run([sys.executable, str(ROOT/'scripts/sourcing.py'), *args], capture_output=True, text=True)
            return p, json.loads(p.stdout) if p.stdout.strip() else {}
        p, output = cli('init', '--run', str(self.path), '--brief', str(brief))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('run_id', output)
        p, output = cli('status', '--run', str(self.path))
        self.assertEqual(output['used_requests'], 0)
        c = self.candidate()
        file = Path(self.tmp.name)/'candidate.json'
        file.write_text(json.dumps(c))
        self.assertEqual(cli('submit', '--run', str(self.path), '--file', str(file))[0].returncode, 0)
        for command in ('validate', 'results'):
            p, output = cli(command, '--run', str(self.path))
            self.assertEqual(output['counts']['qualified'], 1)
        p, output = cli('init', '--run', str(self.path), '--brief', str(brief))
        self.assertEqual(p.returncode, 2)
        self.assertIn('error', output)

    def test_wire_operation_timeout_and_incomplete_body_fail_closed(self):
        self.init()
        self.assertTrue(hasattr(s, 'wire_request'), 'hard network timeout wrapper missing')
        from unittest.mock import patch
        def sleepy(*a):
            import time
            time.sleep(3)
        with patch.object(s, 'wire_request', sleepy):
            before = s.time.monotonic()
            with self.assertRaises(ValueError):
                s.request('https://example.com/job', 0.1, 100, '93.184.216.34')
            self.assertLess(s.time.monotonic() - before, 1)
        r = s.fetch(self.path, 'https://example.com/job', transport=lambda *a: (200, {'content-length': '1000'}, b'short', a[0]))
        self.assertEqual(r['status'], 'error')

    def test_bridge_output_cap_and_malformed_envelope(self):
        self.init()
        from unittest.mock import patch
        import sys
        import shlex
        file = Path(self.tmp.name)/'bridge.py'
        command = shlex.join([sys.executable, str(file)])
        for code in ('print("x" * 10000)', 'print("{}")'):
            file.write_text(code)
            with patch.dict(os.environ, {'SOURCING_SEARCH_COMMAND': command}):
                self.assertEqual(s.search(self.path, 'q', 1)['status'], 'error')

    def test_mandatory_fail_excluded_without_optional_fit_and_bad_brief_rejected(self):
        self.init()
        c = self.candidate()
        c['fit_dimensions'] = []
        c['hard_findings'][0]['status'] = 'fail'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['excluded']), 1)
        other = Path(self.tmp.name)/'bad'
        self.brief['hard_constraints'][0]['mandatory'] = 'false'
        with self.assertRaises(ValueError):
            s.initialize(other, self.brief)

    def test_raw_body_and_linked_json_posting_scope(self):
        self.init()
        c = self.candidate('Acme Engineer Apply now Singapore big tech https://example.com/api/jobs')
        page = s.snapshot(self.path)['evidence'][c['evidence_refs'][0]]
        self.assertIn('raw_body', page)
        self.assertIn('raw_base64', page)
        payload = {'jobs': [{'id': 'one', 'jobUrl': c['url'], 'title': 'Engineer', 'company': 'Acme', 'body': 'Apply now Singapore big tech'},
                            {'id': 'two', 'jobUrl': 'https://example.com/job/2', 'title': 'Other', 'body': 'unrelated fantastic benefits'}]}
        api = s.fetch(self.path, 'https://example.com/api/jobs', transport=lambda *a: (200, {'content-type': 'application/json'}, json.dumps(payload).encode(), a[0]))
        c['posting_id'] = 'one'
        c['source_links'] = [{'ref': page['id'], 'passage': 'https://example.com/api/jobs'}]
        c['evidence_refs'].append(api['id'])
        for q in [*c['identity'].values(), *c['availability_evidence'], *c['hard_findings'], c['fit_dimensions'][0]['job']]:
            q['ref'] = api['id']
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['qualified']), 1)
        c['fit_dimensions'][0]['job']['passage'] = 'unrelated fantastic benefits'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)
        c['fit_dimensions'][0]['job']['passage'] = 'big tech'
        c['posting_id'] = 'two'
        s.submit(self.path, c)
        self.assertEqual(len(s.results(self.path)['unverifiable']), 1)

    def test_cli_explicit_output_and_init_limit_flags(self):
        import subprocess
        import sys
        brief = Path(self.tmp.name)/'brief.json'
        brief.write_text(json.dumps(self.brief))
        out = Path(self.tmp.name)/'init.json'
        p = subprocess.run([sys.executable, str(ROOT/'scripts/sourcing.py'), 'init', '--run', str(self.path), '--brief', str(brief), '--requests', '2', '--seconds', '30', '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(out.read_text())['brief']['limits']['requests'], 2)
        self.assertEqual(s.snapshot(self.path)['brief']['limits']['seconds'], 30)

    def test_search_timeout_includes_backpressured_stdin(self):
        import sys
        import shlex
        file = Path(self.tmp.name)/'bridge.py'
        file.write_text('import time\ntime.sleep(2)\n')
        before = s.time.monotonic()
        with self.assertRaises((ValueError, BrokenPipeError)):
            s.bridge(shlex.join([sys.executable, str(file)]), {'query': '\u00e9'*200000, 'limit': 1}, 0.1, 4096)
        self.assertLess(s.time.monotonic() - before, 1)


class IntakeTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    init = RuntimeTests.init
    def capture(self, body, url='https://example.com/job/1'):
        return s.fetch(self.path, url, transport=lambda *a: (200, {'content-type': 'text/html'}, body.encode(), a[0]))

    def posting(self, **extra):
        return {'@type': 'JobPosting', 'title': 'Engineer',
                'hiringOrganization': {'name': 'Acme'},
                'url': 'https://example.com/job/1',
                'description': '<h2>Requirements</h2><ul><li>Python &amp; SQL</li><li>Three years</li></ul>', **extra}

    def html(self, value):
        return '<p>Enable JavaScript</p><script type="application/ld+json">' + json.dumps(value) + '</script>'

    def test_rejected_metadata_encoded_script_end_cannot_leak(self):
        self.init()
        foreign = self.posting(url='/job/2', description='&lt;/script&gt;&lt;p&gt;FOREIGN_REQUIREMENTS Singapore Apply now&lt;/p&gt;&lt;script&gt;')
        r = self.capture('<p>Visible safe &amp; real page</p>' + self.html(foreign))
        self.assertEqual(r['status'], 'ok')
        self.assertNotIn('posting', r)
        self.assertNotIn('FOREIGN_REQUIREMENTS', r['text'])
        self.assertIn('Visible safe & real page', r['text'])
        self.assertEqual(s.snapshot(self.path)['candidates'], {})

    def test_deep_malformed_metadata_falls_back_and_preserves_capture(self):
        import base64
        import hashlib
        self.brief['limits']['max_bytes'] = 100000
        self.init()
        # Exercise traversal depth, JSON decoder overflow, and partial-selection
        # ambiguity: a shallow match must not win when another branch is lost.
        for depth in (1100, 10000):
            with self.subTest(depth=depth):
                nested = '[' * depth + '0' + ']' * depth
                script = '[' + json.dumps(self.posting()) + ',' + nested + ']'
                body = '<title>Job Application for Engineer at Acme</title><h1>Visible real posting</h1><script type="application/ld+json">' + script + '</script>'
                r = self.capture(body)
                self.assertEqual(r['status'], 'ok')
                self.assertIn('Visible real posting', r['text'])
                self.assertNotIn('posting', r)
                self.assertNotIn('candidate_id', r)
                self.assertEqual(r['raw_body'], body)
                self.assertEqual(base64.b64decode(r['raw_base64']), body.encode())
                self.assertEqual(r['sha256'], hashlib.sha256(body.encode()).hexdigest())
                self.assertEqual(r['text_sha256'], hashlib.sha256(r['text'].encode()).hexdigest())
                self.assertEqual(s.snapshot(self.path)['evidence'][r['id']], r)
        self.assertEqual(s.snapshot(self.path)['candidates'], {})
        self.assertEqual(s.snapshot(self.path)['used_requests'], 2)

    def test_jsonld_description_is_quoteable_structured_evidence(self):
        self.init()
        r = self.capture(self.html(self.posting()))
        self.assertIn('Requirements\n', r['text'])
        self.assertIn('- Python & SQL\n- Three years', r['text'])
        self.assertEqual(r['posting']['company'], 'Acme')
        self.assertEqual(r['posting']['title'], 'Engineer')
        c = {'company': 'Acme', 'title': 'Engineer', 'url': r['url'], 'kind': 'vacancy',
             'availability': 'unverifiable', 'evidence_refs': [r['id']],
             'identity': {k: {'ref': r['id'], 'passage': v} for k, v in [('company', 'Acme'), ('title', 'Engineer')]}}
        self.assertEqual(s.validate(s.snapshot(self.path), c)['reasons'], ['availability unverifiable'])

    def test_jsonld_selection_binds_only_unambiguous_page_posting(self):
        self.brief['limits']['requests'] = 10
        self.init()
        wrong = self.posting(url='https://example.com/job/2', title='Wrong', description='UNRELATED')
        right = self.posting(url='https://EXAMPLE.com/job/1?utm_source=campaign#apply')
        cases = [(wrong, False), ([wrong, self.posting(url=None)], False),
                 (self.posting(url='https://example.com/job/1?source=GoogleJobs'), False),
                 ([wrong, right], True), ({'@graph': [wrong, {**right, '@type': ['Thing', 'JobPosting']}]}, True),
                 ([right, right], False)]
        for payload, selected in cases:
            with self.subTest(payload=payload):
                r = self.capture(self.html(payload))
                self.assertNotIn('UNRELATED', r['text'])
                self.assertEqual(bool(r.get('posting')), selected)
                if selected:
                    self.assertEqual(r['posting']['binding'], 'explicit_url')
                    self.assertEqual(r['posting']['url'], r['url'])

    def test_fallback_and_malformed_metadata_remain_usable_not_invented(self):
        self.init()
        body = '<title>Job Application for Engineer at Acme</title><h1>Engineer</h1><p>Acme</p><h2>Requirements</h2><ul><li>Python</li></ul><script type="application/ld+json">{broken</script>'
        r = self.capture(body)
        self.assertIn('posting', r, 'visible source identity fallback is missing')
        self.assertEqual(r['posting']['binding'], 'visible_page_title')
        self.assertIn('Requirements\n- Python', r['text'])
        self.assertEqual(r['posting']['company'], 'Acme')
        r = self.capture(self.html(self.posting(url=None, description='&amp;lt;h2&amp;gt;Requirements&amp;lt;/h2&amp;gt;&amp;lt;p&amp;gt;SQL&amp;lt;/p&amp;gt;')))
        self.assertEqual(r['posting']['binding'], 'page_url_inferred')
        self.assertIn('Requirements\nSQL', r['text'])
        r = self.capture(self.html(self.posting(title={'bad': True}, hiringOrganization=None, description=[])))
        self.assertEqual(r['status'], 'ok')
        self.assertFalse(r.get('posting'))

    def test_fetch_checkpoints_unknown_candidate_atomically_before_return(self):
        self.init()
        r = self.capture(self.html(self.posting()))
        state = json.loads((self.path / 'state.json').read_text())
        self.assertEqual(len(state['candidates']), 1, 'fetch did not durably checkpoint candidate')
        c = next(iter(state['candidates'].values()))
        self.assertEqual(c['evidence_refs'], [r['id']])
        self.assertEqual(c['availability'], 'unverifiable')
        self.assertEqual(c['hard_findings'], [{'id': 'geo', 'status': 'unknown'}])
        self.assertEqual(c['fit_dimensions'], [])
        self.assertEqual(s.validate(state, c)['reasons'], ['availability unverifiable'])
        with s.locked(self.path) as stored:
            stored['created_at'] -= 100
        import subprocess, sys
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/sourcing.py'), 'status', '--run', str(self.path)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)['candidates'][c['id']], c)
        with self.assertRaises(ValueError):
            self.capture(self.html(self.posting()))

    def test_compact_cli_omits_bulk_without_changing_durable_evidence(self):
        self.init()
        r = self.capture(self.html(self.posting()))
        import subprocess, sys
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/sourcing.py'), 'status', '--run', str(self.path), '--compact'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        e = json.loads(p.stdout)['evidence'][r['id']]
        self.assertEqual(e['text'], r['text'])
        self.assertEqual(e['sha256'], r['sha256'])
        self.assertNotIn('raw_body', e)
        self.assertNotIn('raw_base64', e)
        self.assertNotIn('description', e['posting'])
        self.assertEqual(s.snapshot(self.path)['evidence'][r['id']]['raw_body'], r['raw_body'])

    def test_refetch_keeps_provisional_and_richer_host_record(self):
        self.init()
        r = self.capture(self.html(self.posting()))
        first = next(iter(s.snapshot(self.path)['candidates'].values()))
        r2 = self.capture(self.html(self.posting(description='changed')))
        self.assertEqual(r2['candidate_id'], first['id'])
        self.assertEqual(next(iter(s.snapshot(self.path)['candidates'].values())), first)
        rich = {**first, 'provisional': False, 'host_note': 'retain reviewed gates', 'availability': 'closed',
                'availability_evidence': [{'ref': r['id'], 'passage': 'Engineer'}]}
        rich = s.submit(self.path, rich)
        self.capture(self.html(self.posting()))
        self.assertEqual(s.snapshot(self.path)['candidates'], {rich['id']: rich})

    def test_invalid_supplied_metadata_url_cannot_infer_page_identity(self):
        self.init()
        for value in (0, False, '', [], {}):
            with self.subTest(url=value):
                r = self.capture(self.html(self.posting(url=value)))
                self.assertFalse(r.get('posting'), 'invalid explicit URL became page-bound identity')
                self.assertNotIn('candidate_id', r)
        self.assertEqual(s.snapshot(self.path)['candidates'], {})

    def test_closed_notfound_and_redirect_never_automatically_open(self):
        self.init()
        for message in ('Applications are closed', 'Page not found'):
            r = self.capture('<h1>' + message + '</h1>' + self.html(self.posting()))
            c = s.snapshot(self.path)['candidates'][r['candidate_id']]
            self.assertEqual(c['availability'], 'unverifiable')
            self.assertEqual(s.validate(s.snapshot(self.path), c)['group'], 'unverifiable')
        calls = []
        def redirect(url, *args):
            calls.append(url)
            if len(calls) == 1:
                return 302, {'location': '/careers'}, b'', url
            return 200, {}, b'<h1>Careers</h1>', url
        r = s.fetch(self.path, 'https://example.com/old-job', transport=redirect)
        self.assertEqual(r['url'], 'https://example.com/careers')
        self.assertNotIn('candidate_id', r)
        self.assertEqual(len(s.snapshot(self.path)['candidates']), 1)


if __name__ == '__main__':
    unittest.main()
