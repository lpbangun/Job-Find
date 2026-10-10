// Deployment-owned read-only renderer. Python mediates every resource request.
import './browser_process_group.mjs';
import readline from 'node:readline';
import {randomUUID} from 'node:crypto';
import {loadChromium} from './browser_module.mjs';
const lines = readline.createInterface({input: process.stdin});
const pending = new Map();
let resolveConfig;
const configPromise = new Promise(resolve => { resolveConfig = resolve; });
let configured = false;
lines.on('line', line => {
  const message = JSON.parse(line);
  if (!configured) { configured = true; resolveConfig(message); return; }
  const callback = pending.get(message.id);
  if (callback) { pending.delete(message.id); callback(message); }
});
const send = value => process.stdout.write(JSON.stringify(value) + '\n');
let sequence = 0;
const fetchResource = request => new Promise(resolve => {
  const id = ++sequence;
  pending.set(id, resolve);
  send({kind: 'request', id, url: request.url(), method: request.method(), resource_type: request.resourceType()});
});
const captureDOM = () => {
  const visible = el => {
    if (!el || !el.getClientRects().length) return false;
    for (let p = el; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (p.hidden || p.inert || s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return false;
    }
    return true;
  };
  const enabled = el => !el.matches(':disabled') &&
    !el.closest('[inert], [aria-disabled="true"], [hidden]');
  const label = el => (el.getAttribute('aria-label') || el.innerText || el.value || '').trim().slice(0, 500);
  const allForms = [...document.forms];
  const text = document.body ? document.body.innerText : '';
  const forms = allForms.slice(0, 20).map(form => {
    const all = [...form.elements];
    return {visible: visible(form), context: [form.id, form.name, form.className, form.getAttribute('aria-label') || ''].join(' '),
      action: form.getAttribute('action'),
      overflow: all.length > 200,
      controls: all.slice(0, 200).map(el => ({tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(),
        name: (el.name || '').slice(0, 200), label: label(el), visible: visible(el), enabled: enabled(el),
        editable: !el.readOnly && enabled(el), owned: el.form === form,
        empty: !el.value, value: el.type === 'hidden' ? (el.value || '').slice(0, 500) : null,
        formaction: el.getAttribute('formaction')}))};
  });
  const challenge = [...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[title*="challenge"],[id*="challenge-stage"],[id*="captcha-container"]')].some(visible);
  return {url: location.href, document_title: document.title, rendered_html: document.documentElement.outerHTML, text: text.slice(0, 200000), forms, challenge,
    overflow: text.length > 200000 || allForms.length > 20,
    unsupported_frames: [...document.querySelectorAll('iframe')].some(visible)};
};

let browser;
try {
  const config = await configPromise;
  const chromium = await loadChromium(config.playwright_module);
  const deadline = Date.now() + config.timeout * 1000;
  const closedNotice = new RegExp(config.closed_pattern, 'i');
  const remaining = () => Math.max(1, deadline - Date.now());
  browser = await chromium.launch({headless: true, chromiumSandbox: true,
    ...(config.executable_path ? {executablePath: config.executable_path} : {}),
    args: ['--force-webrtc-ip-handling-policy=disable_non_proxied_udp'], timeout: remaining()});
  const sessionId = randomUUID();
  const context = await browser.newContext({offline: true, serviceWorkers: 'block', acceptDownloads: false});
  const problems = [];
  await context.route('**/*', async route => {
    try {
      const result = await fetchResource(route.request());
      if (result.error) { problems.push(result.error); await route.abort(); }
      else await route.fulfill({status: result.status, headers: result.headers, body: Buffer.from(result.body_base64, 'base64')});
    } catch (error) { problems.push(String(error).slice(0, 500)); }
  });
  await context.routeWebSocket('**/*', websocket => { problems.push('WebSocket request blocked'); websocket.close(); });
  const page = await context.newPage();
  page.on('popup', popup => { problems.push('Popup blocked'); popup.close(); });
  page.on('dialog', dialog => { problems.push('Dialog blocked'); dialog.dismiss(); });
  page.on('download', download => { problems.push('Download blocked'); download.cancel(); });
  await page.goto(config.target.application_url, {waitUntil: 'domcontentloaded', timeout: remaining()});
  await page.waitForLoadState('networkidle', {timeout: remaining()});
  let snapshot;
  while (Date.now() < deadline) {
    snapshot = await page.evaluate(captureDOM);
    if (snapshot.forms.some(form => form.controls.some(c => c.visible && c.enabled && /apply|application/i.test(c.label))) || snapshot.challenge || closedNotice.test(snapshot.text)) break;
    await page.waitForTimeout(Math.min(100, remaining()));
  }
  if (!snapshot) throw new Error('No rendered document captured');
  const rendered_html = snapshot.rendered_html;
  delete snapshot.rendered_html;
  if (Buffer.byteLength(rendered_html) > 1000000) throw new Error('Rendered document exceeds byte limit');
  send({kind: 'result', snapshot, rendered_html, session_id: sessionId, browser_version: browser.version(), problems});
} catch (error) {
  send({kind: 'result', error: String(error).slice(0, 5000)});
} finally {
  if (browser) await browser.close();
  lines.close();
  process.stdin.destroy();
}
