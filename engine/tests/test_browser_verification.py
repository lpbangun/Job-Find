"""Offline policy tests. Mock observations are not live application evidence."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from jobrouter.browser_verification import BrowserPolicy, BrowserApplicationVerifier, _target, _evaluate
from jobrouter.matching import screen
from jobrouter.models import Brief, Evidence, Job, now
from jobrouter.transport import FetchError, Response, PublicFetcher
from jobrouter.verification import verify_application


def fixture_job(provider='lever'):
    url = 'https://jobs.lever.co/example/abc'
    if provider == 'structured':
        url = 'https://careers.example.com/jobs/abc'
    job = Job(provider, 'example', 'abc', 'Software Engineer', 'Example', url, 'Build software.')
    job.evidence.append(Evidence.from_text(url, job.description, job.description, 'description'))
    return job


def control(tag, kind, name='', label=''):
    return dict(tag=tag, type=kind, name=name, label=label, visible=True, enabled=True,
                editable=True, owned=True, empty=True, value=None, formaction=None)


def fixture_capture(target, nonce='test-nonce'):
    raw = '<h1>Software Engineer</h1><form><input name="name"><input type="email" name="email"><button type="button">Submit application</button></form>'
    return dict(nonce=nonce, provider='node-playwright-chromium', source_kind='live',
        browser_version='unit-fixture-not-a-live-browser', session_id='unit-fixture-session',
        started_at=now(), observed_at=now(), target=target, rendered_html=raw,
        rendered_sha256=hashlib.sha256(raw.encode()).hexdigest(), problems=[],
        fetch_receipts=[dict(url=target['application_url'], status=200, sha256=hashlib.sha256(raw.encode()).hexdigest())],
        snapshot=dict(url=target['application_url'], text='Example Software Engineer Submit application',
            document_title='Example Software Engineer', challenge=False, overflow=False, unsupported_frames=False,
            forms=[dict(visible=True, overflow=False, context='application-form', action=None,
                        controls=[control('input','text','name'), control('input','email','email'),
                                  control('button','button',label='Submit application')])]))


class BrowserVerificationTests(unittest.TestCase):
    def setUp(self):
        self.policy = BrowserPolicy(allowed_hosts=('jobs.lever.co', 'careers.example.com'))
        self.job = fixture_job()
        self.target = _target(self.job, self.policy)
        self.capture = fixture_capture(self.target)

    def evaluate(self, capture=None):
        return _evaluate(capture or self.capture, self.target, 'test-nonce', self.policy)

    def test_js_button_no_explicit_post_action_can_establish_open_path(self):
        self.assertEqual(self.evaluate()[0], 'open')

    def test_closed_notice_is_not_an_open_form(self):
        self.capture['snapshot']['text'] += ' This job is closed.'
        self.assertEqual(self.evaluate()[0], 'closed')

    def test_official_url_and_identity_are_exact(self):
        for key, value in [('url','https://jobs.lever.co/example/other/apply'), ('text','Unrelated vacancy')]:
            capture = deepcopy(self.capture)
            capture['snapshot'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.evaluate(capture)
        self.job.external_id = 'other'
        with self.assertRaises(ValueError):
            _target(self.job, self.policy)

    def test_synthetic_or_unbound_provenance_rejected(self):
        for key, value in [('source_kind','fixture'), ('nonce','other'), ('provider','model-assertion'),
                           ('target',{}), ('browser_version',''), ('session_id','')]:
            capture = deepcopy(self.capture); capture[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.evaluate(capture)

    def test_expired_future_naive_and_reversed_times_rejected(self):
        current = datetime.now(timezone.utc)
        for started, observed in ((current-timedelta(hours=1), current),
                                  (current, current+timedelta(seconds=30)),
                                  (current, current-timedelta(seconds=1))):
            capture = deepcopy(self.capture)
            capture.update(started_at=started.isoformat(), observed_at=observed.isoformat())
            with self.subTest(started=started), self.assertRaises(ValueError):
                self.evaluate(capture)
        self.capture['started_at'] = '2026-01-01T00:00:00'
        with self.assertRaises(ValueError): self.evaluate()

    def test_shell_challenge_blocked_resources_and_oversized_capture_rejected(self):
        for field in ('challenge','overflow','unsupported_frames'):
            capture=deepcopy(self.capture);capture['snapshot'][field]=True
            with self.subTest(field=field), self.assertRaises(ValueError): self.evaluate(capture)
        self.capture['problems']=['CSS blocked']
        with self.assertRaises(ValueError): self.evaluate()
        self.capture['problems']=[]; self.capture['snapshot']['forms']=[]
        with self.assertRaises(ValueError): self.evaluate()

    def test_identity_fields_must_be_editable_visible_owned_enabled_and_empty(self):
        for field in ('editable','visible','owned','enabled','empty'):
            capture=deepcopy(self.capture);capture['snapshot']['forms'][0]['controls'][0][field]=False
            with self.subTest(field=field), self.assertRaises(ValueError): self.evaluate(capture)

    def test_submit_control_must_be_visible_enabled_and_application_labeled(self):
        for field,value in (('visible',False),('enabled',False),('owned',False),('label','Subscribe'),('type','reset')):
            capture=deepcopy(self.capture);capture['snapshot']['forms'][0]['controls'][2][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): self.evaluate(capture)

    def test_newsletter_and_conflicting_job_binding_rejected(self):
        for action in ('https://attacker.example/submit','/example/other/apply'):
            capture=deepcopy(self.capture);capture['snapshot']['forms'][0]['action']=action
            with self.subTest(action=action), self.assertRaises(ValueError): self.evaluate(capture)
        self.capture['snapshot']['forms'][0]['context']='newsletter-form'
        with self.assertRaises(ValueError): self.evaluate()
        self.capture['snapshot']['forms'][0]['context']='application-form'
        hidden=control('input','hidden','jobId');hidden['value']='different-job'
        self.capture['snapshot']['forms'][0]['controls'].append(hidden)
        with self.assertRaises(ValueError): self.evaluate()

    def test_raw_hash_and_document_receipt_required(self):
        self.capture['rendered_html'] += 'changed'
        with self.assertRaises(ValueError): self.evaluate()
        self.capture=fixture_capture(self.target);self.capture['fetch_receipts']=[]
        with self.assertRaises(ValueError): self.evaluate()

    def test_shared_adapter_supports_canonical_generic_forms(self):
        job=fixture_job('structured');target=_target(job,self.policy)
        self.assertEqual(target['application_url'],job.url)
        self.assertEqual(_evaluate(fixture_capture(target),target,'test-nonce',self.policy)[0],'open')
        job.evidence=[]
        with self.assertRaises(ValueError): _target(job,self.policy)

    def test_provider_mutates_only_after_internal_capture_and_records_short_expiry(self):
        provider=BrowserApplicationVerifier(self.policy)
        def fake_capture(target,timeout,nonce): return fixture_capture(target,nonce)
        with patch.object(provider,'_capture',fake_capture):
            result=provider.verify(self.job)
        self.assertEqual(result['status'],'open');self.assertIs(result['submission_tested'],False)
        self.assertEqual(self.job.evidence[-1].field,'rendered_application_form')
        self.assertIsNotNone(self.job.evidence[-1].expires_at)
        self.assertEqual(screen(self.job,Brief('Find jobs')).checks[0].verdict,'pass')
        self.job.evidence[-1].expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        self.assertEqual(screen(self.job,Brief('Find jobs')).checks[0].verdict,'unknown')

    def test_missing_runtime_and_forged_fixture_fail_closed(self):
        provider=BrowserApplicationVerifier(self.policy)
        with patch.object(provider,'_capture',return_value={'error':'Sandboxed Chromium unavailable'}):
            self.assertEqual(provider.verify(self.job)['status'],'unverified')
        self.assertFalse(any(e.field=='rendered_application_form' for e in self.job.evidence))

    def test_static_access_failure_does_not_trigger_browser_retry(self):
        provider=BrowserApplicationVerifier(self.policy)
        fetcher=Mock();fetcher.get.side_effect=FetchError('Access stopped: HTTP 403')
        with patch.object(provider,'verify') as browser:
            self.assertEqual(verify_application(self.job,fetcher,provider)['status'],'unverified')
            browser.assert_not_called()

    def test_successful_static_fetch_can_use_real_provider_but_not_arbitrary_callback(self):
        fetcher=Mock();fetcher.get.return_value=Response(self.target['application_url'],200,{},b'<h1>Software Engineer</h1><div id="app"></div>',now())
        provider=BrowserApplicationVerifier(self.policy)
        with patch.object(provider,'verify',return_value={'status':'unverified','submission_tested':False}) as browser:
            verify_application(self.job,fetcher,provider);browser.assert_called_once_with(self.job)
        forged=Mock()
        self.assertEqual(verify_application(self.job,fetcher,forged)['status'],'unverified')
        forged.verify.assert_not_called()

    def test_policy_limits_and_host_allowlist(self):
        for kwargs in ({'timeout':0},{'max_parallel':0},{'max_age_seconds':float('inf')},
                       {'allowed_hosts':('localhost',)},{'trusted_proxy_hosts':('evil.example',)}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                BrowserPolicy(**({'allowed_hosts':('jobs.lever.co',)}|kwargs))

    def test_extra_ats_route_and_generic_employer_conflict_rejected(self):
        self.job.url += '/unrelated'
        with self.assertRaises(ValueError): _target(self.job,self.policy)
        job=fixture_job('structured');target=_target(job,self.policy);capture=fixture_capture(target)
        capture['snapshot']['text']='Different Employer Software Engineer Submit application'
        capture['snapshot']['document_title']='Different Employer'
        with self.assertRaises(ValueError): _evaluate(capture,target,'test-nonce',self.policy)

    def test_redirect_rejected_before_any_second_host_request(self):
        calls=[]
        def wire(url):
            calls.append(url)
            if url.endswith('/robots.txt'): return Response(url,200,{},b'',now())
            return Response(url,302,{'location':'https://not-approved.example/next'},b'',now())
        fetcher=PublicFetcher(wire=wire,per_origin_delay=0)
        with self.assertRaisesRegex(FetchError,'Redirects disabled'):
            fetcher.get('https://jobs.lever.co/example/abc/apply',follow_redirects=False)
        self.assertEqual(calls,['https://jobs.lever.co/robots.txt','https://jobs.lever.co/example/abc/apply'])

    def test_rejected_capture_keeps_network_receipts(self):
        provider=BrowserApplicationVerifier(self.policy)
        def captured(target,timeout,nonce):
            value=fixture_capture(target,nonce)
            value['snapshot']['challenge']=True
            value['accounting_complete']=True
            return value
        with patch.object(provider,'_capture',captured): result=provider.verify(self.job)
        self.assertEqual(result['status'],'unverified')
        self.assertEqual(len(result['fetch_receipts']),1)
        self.assertTrue(result['accounting_complete'])

    def test_interrupted_capture_recovers_observed_receipts_without_claiming_complete_count(self):
        provider=BrowserApplicationVerifier(self.policy)
        def interrupted(command,encoded,timeout,limit):
            request=json.loads(encoded)
            Path(request['progress_path']).write_text(json.dumps({
                'fetch_receipts':[{'url':self.target['application_url'],'status':200}],
                'resource_receipts':[{'url':'https://jobs.lever.co/slow.js','status':'pending'}],
                'accounting_complete':False}))
            raise RuntimeError('Capture interrupted')
        with patch('jobrouter.browser_verification._run_host',interrupted): result=provider.verify(self.job)
        self.assertEqual(result['status'],'unverified')
        self.assertEqual(len(result['fetch_receipts']),1)
        self.assertFalse(result['accounting_complete'])
        self.assertEqual(result['resource_receipts'][0]['status'],'pending')

    def test_expired_posting_and_speculative_pool_do_not_launch_browser(self):
        provider=BrowserApplicationVerifier(self.policy)
        with patch.object(provider,'_capture') as capture:
            self.job.deadline=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
            self.assertEqual(provider.verify(self.job)['status'],'closed')
            self.job.deadline=None; self.job.title='General Application'
            self.assertEqual(provider.verify(self.job)['status'],'lead')
            capture.assert_not_called()
