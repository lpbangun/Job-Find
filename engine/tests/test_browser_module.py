"""Real Node import interoperability, without browser launch or network."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import jobrouter


@unittest.skipUnless(shutil.which('node'), 'Requires Node module loader')
class BrowserModuleTests(unittest.TestCase):
    def test_named_default_and_commonjs_exports(self):
        loader = (Path(jobrouter.__file__).parent / 'browser_module.mjs').as_uri()
        variants = {
            'named.mjs': 'export const chromium = {launch(){return "ok"}};',
            'default.mjs': 'export default {chromium:{launch(){return "ok"}}};',
            # Computed key prevents Node from synthesizing a named CJS export.
            'index.js': 'const key="chrom"+"ium"; module.exports = {[key]:{launch(){return "ok"}}};',
        }
        with tempfile.TemporaryDirectory() as directory:
            for filename, source in variants.items():
                path = Path(directory) / filename
                path.write_text(source)
                for specifier in (str(path), path.as_uri()):
                    with self.subTest(specifier=specifier):
                        script = f'import {{loadChromium}} from {json.dumps(loader)}; const c=await loadChromium({json.dumps(specifier)}); console.log(c.launch());'
                        result = subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(result.stdout.strip(),'ok')

    def test_missing_launch_api_is_rejected(self):
        loader = (Path(jobrouter.__file__).parent / 'browser_module.mjs').as_uri()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.cjs'
            path.write_text('module.exports={chromium:{}};')
            script = f'import {{loadChromium}} from {json.dumps(loader)}; await loadChromium({json.dumps(str(path))});'
            result = subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('no Chromium launch API',result.stderr)
