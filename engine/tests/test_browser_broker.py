"""Broker protocol fixtures; no browser or external network is launched."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from jobrouter.browser_capture import capture
from jobrouter.browser_verification import BrowserPolicy, _target
from test_browser_verification import fixture_job


class BrowserBrokerTests(unittest.TestCase):
    def run_broker(self,method='GET',url=None,budget=5,pending=0,requests=1,error=None):
        target=_target(fixture_job(),BrowserPolicy(allowed_hosts=('jobs.lever.co',)))
        request=dict(target=target,allowed_hosts=['jobs.lever.co'],trusted_proxy_hosts=[],timeout=3,
                     request_budget=budget,max_response_bytes=1000,max_total_bytes=2000,node_executable='fixture-node',
                     fixture_html='<h1>Software Engineer</h1>',nonce='fixture')
        message=dict(kind='result',rendered_html='<h1>Software Engineer</h1>',snapshot={},
                     browser_version='fixture-not-live',session_id='fixture',problems=[],pending_requests=pending,stage='snapshot')
        if error:
            message.update(error=error,problems=[{'reason_code':'browser_request_failed'}])
        process=Mock(returncode=0)
        process.stdin=io.StringIO()
        process.stdout=io.StringIO(json.dumps(dict(kind='stage',stage='navigation'))+'\n'+(json.dumps(dict(kind='request',id=1,url=url or target['application_url'],method=method,resource_type='document',stage='navigation'))+'\n')*requests+json.dumps(message)+'\n')
        process.poll.return_value=0
        with tempfile.TemporaryDirectory() as directory:
            request['progress_path']=str(Path(directory)/'progress.json')
            with patch('jobrouter.browser_capture.subprocess.Popen',return_value=process): result=capture(request)
            progress=json.loads(Path(request['progress_path']).read_text())
        return result,progress

    def test_successful_exit_marks_accounting_complete(self):
        result,progress=self.run_broker()
        self.assertTrue(result['accounting_complete'])
        self.assertTrue(progress['accounting_complete'])
        self.assertEqual(result['resource_receipts'][0]['status'],'completed')
        self.assertEqual(result['source_kind'],'fixture')
        self.assertFalse(result['fetch_receipts'])

    def test_post_is_blocked_and_recorded_without_network(self):
        result,progress=self.run_broker('POST')
        self.assertTrue(result['problems'])
        self.assertEqual(result['resource_receipts'][0]['status'],'failed')
        self.assertFalse(result['fetch_receipts'])
        self.assertTrue(result['accounting_complete'])

    def test_policy_diagnostics_distinguish_method_host_and_budget(self):
        for kwargs, reason in (({'method':'POST'},'method_denied'),
                               ({'url':'https://unknown.example/asset.js'},'host_denied'),
                               ({'budget':1,'requests':2},'request_budget')):
            with self.subTest(reason=reason):
                result,progress=self.run_broker(**kwargs)
                resource=result['resource_receipts'][-1]
                self.assertEqual(resource['reason_code'],reason)
                self.assertEqual(resource['method'],kwargs.get('method','GET'))
                self.assertEqual(resource['resource_type'],'document')
                self.assertEqual(resource['renderer_stage'],'navigation')
                self.assertIn('finished_at',resource)
                self.assertFalse(result['fetch_receipts'])
                self.assertTrue(result.get('problems') or result.get('error'))

    def test_pending_renderer_resources_cannot_be_complete(self):
        result,progress=self.run_broker(pending=1)
        self.assertIn('remain pending',result['error'])
        self.assertFalse(result['accounting_complete'])
        self.assertFalse(progress['accounting_complete'])
        self.assertEqual(result['renderer_stage'],'snapshot')
        self.assertEqual(progress['stage'],'renderer_result')

    def test_invalid_urls_cannot_evade_hard_request_budget(self):
        for url in ('data:text/plain,blocked', 'https://unknown.example/'+'x'*8200):
            with self.subTest(url=url[:40]):
                result,progress=self.run_broker(url=url,budget=1,requests=5)
                self.assertEqual(len(result['resource_receipts']),2)
                self.assertEqual(result['resource_receipts'][-1]['reason_code'],'request_budget')
                self.assertFalse(result['accounting_complete'])
                self.assertIn('budget exhausted',result['error'])
                self.assertFalse(result['fetch_receipts'])

    def test_renderer_error_preserves_accumulated_browser_failures(self):
        result,progress=self.run_broker(error='DOM readiness timeout')
        self.assertEqual(result['browser_problems'][0]['reason_code'],'browser_request_failed')
        self.assertEqual(progress['browser_problems'],result['browser_problems'])
        self.assertFalse(result['accounting_complete'])
