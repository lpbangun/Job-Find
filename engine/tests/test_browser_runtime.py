"""Opt-in real sandboxed browser fixtures; never contact an external site.

Run only on an authorized runtime supporting sandboxed Chromium. A skipped test
is not rendering evidence. Fixture captures cannot qualify jobs as live/open.
"""
import os
import unittest
from jobrouter.browser_verification import BrowserPolicy, BrowserApplicationVerifier, _target, _evaluate, _classify_snapshot
from test_browser_verification import fixture_job


@unittest.skipUnless(os.environ.get('JOBROUTER_BROWSER_TESTS') == '1', 'Requires authorized sandboxed Chromium runtime')
class BrowserRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.provider=BrowserApplicationVerifier(BrowserPolicy(
            allowed_hosts=('jobs.lever.co','careers.example.com'),
            node_executable=os.environ.get('JOBROUTER_NODE','node'),
            playwright_module=os.environ.get('JOBROUTER_PLAYWRIGHT_MODULE','playwright-core'),
            executable_path=os.environ.get('JOBROUTER_CHROMIUM'),timeout=15))

    def capture(self,html,provider='lever'):
        target=_target(fixture_job(provider),self.provider.policy)
        capture=self.provider._capture(target,15,'fixture-nonce',html)
        self.assertNotIn('error',capture,capture.get('error'))
        self.assertEqual(capture['source_kind'],'fixture')
        self.assertFalse(capture['fetch_receipts'],'No public network used by fixtures')
        with self.assertRaises(ValueError): _evaluate(capture,target,'fixture-nonce',self.provider.policy)
        return capture['snapshot']

    def test_static_form_capture(self):
        snap=self.capture('<h1>Example Software Engineer</h1><form><input name="name"><input name="email" type="email"><button>Submit application</button></form>')
        self.assertTrue(snap['forms'][0]['controls'][2]['visible'])
        self.assertEqual(_classify_snapshot(snap,_target(fixture_job(),self.provider.policy))[0],'open')

    def test_delayed_javascript_form_on_second_site_type(self):
        snap=self.capture('''<h1>Example Software Engineer</h1><div id="app"></div><script>
          setTimeout(()=>{document.querySelector('#app').innerHTML='<form><input name="name"><input type="email" name="email"><button type="button">Submit application</button></form>'},200);
          </script>''','structured')
        self.assertEqual(snap['forms'][0]['controls'][2]['type'],'button')
        self.assertTrue(snap['forms'][0]['controls'][2]['enabled'])
        self.assertEqual(_classify_snapshot(snap,_target(fixture_job('structured'),self.provider.policy))[0],'open')

    def test_disabled_and_hidden_controls_are_observed(self):
        snap=self.capture('<h1>Software Engineer</h1><form><input name="name" disabled><input name="email" type="email"><button type="button">Apply</button><button style="display:none">Apply hidden</button></form>')
        self.assertFalse(snap['forms'][0]['controls'][0]['enabled'])
        self.assertFalse(snap['forms'][0]['controls'][3]['visible'])
        with self.assertRaises(ValueError): _classify_snapshot(snap,_target(fixture_job(),self.provider.policy))

    def test_closed_notice_without_form_is_captured(self):
        snap=self.capture('<h1>Software Engineer</h1><p>This job is closed.</p>')
        self.assertEqual(_classify_snapshot(snap,_target(fixture_job(),self.provider.policy))[0],'closed')
