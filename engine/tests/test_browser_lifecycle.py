"""Exercise the actual Node spawn boundary without opening Chromium or a network."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from jobrouter.routing import _run_host, ModelError
import jobrouter


def process_snapshot(path):
    """Read one Linux process identity atomically with respect to disappearance.

    ENOENT/ESRCH mean it stopped. Permission, malformed data and other I/O errors
    must surface instead of manufacturing successful cleanup evidence.
    """
    try:
        fields = path.read_text().rsplit(') ', 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return fields[0], fields[19]


def same_process_running(path, started):
    snapshot = process_snapshot(path)
    return snapshot is not None and snapshot[1] == started and snapshot[0] != 'Z'


class ProcessSnapshotTests(unittest.TestCase):
    def test_disappearance_during_read_is_stopped(self):
        for error in (FileNotFoundError(), ProcessLookupError()):
            with self.subTest(error=type(error).__name__), patch.object(Path, 'read_text', side_effect=error):
                self.assertFalse(same_process_running(Path('/fixture/stat'), '100'))

    def test_permission_and_unexpected_io_errors_surface(self):
        for error in (PermissionError(), OSError('unexpected I/O failure')):
            with self.subTest(error=type(error).__name__), patch.object(Path, 'read_text', side_effect=error):
                with self.assertRaises(type(error)):
                    same_process_running(Path('/fixture/stat'), '100')

    def test_identity_reuse_zombie_and_live_states(self):
        for state, started, expected in (('S','100',True),('Z','100',False),('S','101',False)):
            fields = [state]+['0']*18+[started]
            with self.subTest(state=state,started=started), patch.object(Path, 'read_text', return_value='42 (name with ) spaces) '+' '.join(fields)):
                self.assertEqual(same_process_running(Path('/fixture/stat'),'100'),expected)

    def test_malformed_stat_is_not_successful_cleanup(self):
        with patch.object(Path, 'read_text', return_value='malformed'):
            with self.assertRaises(IndexError):
                same_process_running(Path('/fixture/stat'),'100')


@unittest.skipUnless(os.name == 'posix' and shutil.which('node'), 'POSIX Node lifecycle fixture')
class BrowserLifecycleTests(unittest.TestCase):
    def exercise_cleanup(self, startup_delay=0):
        module = (Path(jobrouter.__file__).parent / 'browser_process_group.mjs').as_uri()
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'child.json'
            # Atomic readiness publication means the child exists and its group
            # can be checked before the cleanup timeout experiment starts.
            child = ("import os,json,time,pathlib,sys; "
                     f"time.sleep({startup_delay}); path=pathlib.Path({str(pidfile)!r}); "
                     "tmp=path.with_suffix('.tmp'); "
                     "tmp.write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgid(0),'owner':int(sys.argv[1])})); "
                     "tmp.replace(path); time.sleep(30)")
            script = (f"import {json.dumps(module)}; import cp from 'node:child_process'; "
                      f"cp.spawn({json.dumps(sys.executable)}, ['-c',{json.dumps(child)},String(process.pid)], "
                      "{detached:true,stdio:'ignore'}); setInterval(()=>{},1000);")
            command = ['node', '--input-type=module', '-e', script]
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, shell=False, start_new_session=True)
            data = None
            try:
                startup_deadline = time.monotonic() + 10
                while not pidfile.exists():
                    if proc.poll() is not None:
                        self.fail('Fixture exited before readiness: ' + proc.stderr.read(4096).decode(errors='replace'))
                    if time.monotonic() >= startup_deadline:
                        self.fail('Fixture readiness was not published within its bounded startup window')
                    time.sleep(.01)
                data = json.loads(pidfile.read_text())
                stat = Path('/proc') / str(data['pid']) / 'stat'
                linux_proc = Path('/proc').is_dir()
                started = None
                if linux_proc:
                    snapshot = process_snapshot(stat)
                    self.assertIsNotNone(snapshot, 'Ready child must exist before timeout')
                    started = snapshot[1]
                # Adopt the already-started real process solely to test timeout
                # cleanup after readiness. Production launch/deadline behavior is
                # unchanged and remains covered by the command-runner tests.
                with patch('jobrouter.routing.subprocess.Popen', return_value=proc) as launch:
                    with self.assertRaisesRegex(ModelError, 'deadline exceeded'):
                        _run_host(command, '{}', 1.5, 10000)
                    launch.assert_called_once_with(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                   stderr=subprocess.PIPE, shell=False, start_new_session=True)
                self.assertEqual(data['pgid'], data['owner'], 'Child must stay in the supervised Node process group')
                self.assertEqual(data['owner'], proc.pid)
                # Assertions precede teardown: teardown must not mask failed
                # runner cleanup. A killed orphan may await init as a zombie.
                def running():
                    if linux_proc:
                        return same_process_running(stat, started)
                    try:
                        os.kill(data['pid'], 0)
                    except ProcessLookupError:
                        return False
                    return True
                for _ in range(30):
                    if not running():
                        break
                    time.sleep(.05)
                self.assertFalse(running(), 'Child still running after supervisor timeout')
            finally:
                # Safety cleanup also covers a failed startup or group assertion.
                groups = {proc.pid}
                if data is not None:
                    groups.add(data['pgid'])
                for group in groups:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                proc.wait()
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()

    def test_detached_spawn_request_stays_in_supervised_group_and_is_stopped(self):
        self.exercise_cleanup()

    def test_startup_longer_than_cleanup_timeout_is_synchronized(self):
        # A startup delay exceeding 1.5 s deterministically exposed the old race.
        self.exercise_cleanup(startup_delay=2)
