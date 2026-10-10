"""Exercise the actual Node spawn boundary without opening Chromium or a network."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from jobrouter.routing import _run_host, ModelError
import jobrouter


@unittest.skipUnless(os.name == 'posix' and shutil.which('node'), 'POSIX Node lifecycle fixture')
class BrowserLifecycleTests(unittest.TestCase):
    def test_detached_spawn_request_stays_in_supervised_group_and_is_stopped(self):
        module=(Path(jobrouter.__file__).parent/'browser_process_group.mjs').as_uri()
        with tempfile.TemporaryDirectory() as directory:
            pidfile=Path(directory)/'child.json'
            child="import os,json,time,pathlib,sys; pathlib.Path("+repr(str(pidfile))+ ").write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgid(0),'owner':int(sys.argv[1])})); time.sleep(30)"
            script=f"import {json.dumps(module)}; import cp from 'node:child_process'; cp.spawn({json.dumps(sys.executable)}, ['-c',{json.dumps(child)},String(process.pid)], {{detached:true,stdio:'ignore'}}); setInterval(()=>{{}},1000);"
            with self.assertRaisesRegex(ModelError,'deadline exceeded'):
                _run_host(['node','--input-type=module','-e',script],'{}',1.5,10000)
            self.assertTrue(pidfile.exists(),'Fixture must have started')
            data=json.loads(pidfile.read_text())
            self.assertEqual(data['pgid'],data['owner'],'Child must stay in the supervised Node process group')
            # A killed orphan may briefly remain a zombie pending init reaping.
            stat=Path('/proc')/str(data['pid'])/'stat'
            def running():
                if stat.exists() and stat.read_text().split(') ')[1][0]=='Z': return False
                try: os.kill(data['pid'],0)
                except ProcessLookupError: return False
                return True
            for _ in range(30):
                if not running(): break
                time.sleep(.05)
            self.assertFalse(running(),'Child still running after supervisor timeout')
