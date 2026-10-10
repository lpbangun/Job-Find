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
    def run_broker(self,method='GET'):
        target=_target(fixture_job(),BrowserPolicy(allowed_hosts=('jobs.lever.co',)))
        request=dict(target=target,allowed_hosts=['jobs.lever.co'],trusted_proxy_hosts=[],timeout=3,
                     request_budget=5,max_response_bytes=1000,max_total_bytes=2000,node_executable='fixture-node',
                     fixture_html='<h1>Software Engineer</h1>',nonce='fixture')
        message=dict(kind='result',rendered_html='<h1>Software Engineer</h1>',snapshot={},
                     browser_version='fixture-not-live',session_id='fixture',problems=[])
        process=Mock(returncode=0)
        process.stdin=io.StringIO()
        process.stdout=io.StringIO(json.dumps(dict(kind='request',id=1,url=target['application_url'],method=method,resource_type='document'))+'\n'+json.dumps(message)+'\n')
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
