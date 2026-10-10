// Deployment-selected existing Playwright package, supporting ESM and CommonJS.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
export async function loadChromium(specifier) {
  const url = specifier.startsWith('file:') ? specifier : pathToFileURL(createRequire(import.meta.url).resolve(specifier)).href;
  const module = await import(url);
  const chromium = module.chromium ?? module.default?.chromium;
  if (!chromium || typeof chromium.launch !== 'function') {
    throw new Error('Configured Playwright module has no Chromium launch API');
  }
  return chromium;
}
