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

    @unittest.skipUnless(os.name == 'posix' and os.path.isdir('/proc'), 'Linux process-group inspection')
    def test_real_chromium_is_stopped_after_supervisor_timeout(self):
        """Withhold a broker reply after actual Chromium starts, then time out.

        The browser stays offline; no HTTP fetch is made. Startup readiness is
        separate from the short supervisor timeout, avoiding load-dependent races.
        """
        import json
        from pathlib import Path
        import select
        import signal
        import subprocess
        import time
        from unittest.mock import patch
        import jobrouter
        from jobrouter.routing import _run_host, ModelError

        script = Path(jobrouter.__file__).parent / 'browser_capture.mjs'
        command = [self.provider.policy.node_executable, str(script)]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=False, start_new_session=True)
        def processes():
            members = {}
            for path in Path('/proc').glob('[0-9]*/stat'):
                try:
                    fields = path.read_text().rsplit(') ', 1)[1].split()
                    members[int(path.parent.name)] = {
                        'state': fields[0], 'parent': int(fields[1]),
                        'group': int(fields[2]), 'started': fields[19]}
                except (OSError, ValueError, IndexError):
                    continue
            return members
        observed = {}
        try:
            config = {'playwright_module': self.provider.policy.playwright_module,
                      'executable_path': self.provider.policy.executable_path,
                      'timeout': 60, 'closed_pattern': 'This job is closed',
                      'target': _target(fixture_job(), self.provider.policy)}
            proc.stdin.write((json.dumps(config)+'\n').encode())
            proc.stdin.flush()
            ready, _, _ = select.select([proc.stdout], [], [], 20)
            self.assertTrue(ready, 'Renderer did not reach bounded startup readiness')
            message = json.loads(proc.stdout.readline())
            self.assertEqual(message.get('kind'), 'request', message)
            self.assertEqual(message.get('resource_type'), 'document', message)
            self.assertEqual(message.get('url'), config['target']['application_url'])
            # A real page-generated resource request proves launch/newPage/goto
            # ran. Record exact process identities before withholding its reply.
            current = processes()
            owned = {proc.pid}
            while True:
                descendants = {pid for pid, info in current.items() if info['parent'] in owned}
                if descendants <= owned:
                    break
                owned.update(descendants)
            owned.update(pid for pid, info in current.items() if info['group'] == proc.pid)
            observed = {pid: current[pid] for pid in owned if pid in current}
            self.assertIn(proc.pid, observed)
            self.assertGreater(len(observed), 1, 'Actual Chromium descendants must be observed')
            self.assertTrue(all(info['group'] == proc.pid for info in observed.values()),
                            'Every observed browser descendant must share the supervisor group')
            with patch('jobrouter.routing.subprocess.Popen', return_value=proc) as launch:
                with self.assertRaisesRegex(ModelError, 'deadline exceeded'):
                    _run_host(command, '', 1.5, 10000)
                launch.assert_called_once_with(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, shell=False, start_new_session=True)
            def remaining_owned():
                current = processes()
                # Check exact recorded process identities even if they changed
                # groups, plus newly spawned members of the supervised group.
                return {pid: info for pid, info in current.items()
                        if info['group'] == proc.pid or
                        (pid in observed and info['started'] == observed[pid]['started'])}
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if not any(info['state'] != 'Z' for info in remaining_owned().values()):
                    break
                time.sleep(.05)
            self.assertFalse({pid: info for pid, info in remaining_owned().items() if info['state'] != 'Z'},
                             'Browser process still running after supervisor timeout')
            # Killed orphans may briefly await init reaping as zombies. They are
            # reported separately, never counted as still-running browsers.
            zombies = [pid for pid, info in remaining_owned().items() if info['state'] == 'Z']
            print('Chromium timeout cleanup: stopped processes; unreaped zombie PIDs:', zombies)
        finally:
            # Assertions precede safety teardown so it cannot manufacture a pass.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for pid, info in processes().items():
                if pid in observed and info['started'] == observed[pid]['started']:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
