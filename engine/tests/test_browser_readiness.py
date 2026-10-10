"""Deterministic real-Node readiness gate tests; no browser/network."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import jobrouter


@unittest.skipUnless(shutil.which('node'), 'Requires Node')
class BrowserReadinessTests(unittest.TestCase):
    def test_stability_pending_dependencies_and_late_changes(self):
        module = (Path(jobrouter.__file__).parent / 'browser_readiness.mjs').as_uri()
        script = f'''import {{readinessGate}} from {json.dumps(module)};
          import assert from 'node:assert/strict';
          const ready=readinessGate(500), form={{form:'enabled'}}, challenge={{challenge:true}};
          assert.equal(ready(form,0,true,0),false);
          assert.equal(ready(form,0,true,499),false);
          assert.equal(ready(form,1,true,500),false); // unknown dependency resets
          assert.equal(ready(form,0,true,600),false);
          assert.equal(ready(challenge,0,true,1000),false); // late challenge resets
          assert.equal(ready(challenge,0,true,1500),true); // classifier still rejects challenge
          assert.equal(ready(form,0,false,1600),false); // missing controls never ready
          assert.equal(ready(form,0,true,1700),false);
          assert.equal(ready(form,0,true,2200),true);
        '''
        result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_browser_failure_remains_fatal_after_request_settles(self):
        module = (Path(jobrouter.__file__).parent / 'browser_readiness.mjs').as_uri()
        script = f'''import {{trackRequests}} from {json.dumps(module)};
          import assert from 'node:assert/strict';
          const handlers={{}}, problems=[];
          const active=trackRequests({{on:(event,handler)=>handlers[event]=handler}},()=>"dom_readiness",problems);
          const request={{url:()=>"https://example.com/app.js",method:()=>"GET",resourceType:()=>"script",failure:()=>({{errorText:"net::ERR_FAILED"}})}};
          handlers.request(request);
          assert.equal(active.size,1);
          handlers.requestfailed(request);
          assert.equal(active.size,0);
          assert.equal(problems.length,1);
          assert.equal(problems[0].reason_code,"browser_request_failed");
          assert.equal(problems[0].resource_type,"script");
          assert.equal(problems[0].stage,"dom_readiness");
        '''
        result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
