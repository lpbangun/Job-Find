# Optional rendered application-path verification

This MVP extends the existing Python engine; it does not replace its HTTP transport, static verifier or model router. A deployment-owned Node/Playwright worker opens a fresh sandboxed Chromium context. Python fulfills its GET resource requests through `PublicFetcher`, preserving robots checks, public HTTPS/DNS pinning or explicitly configured trusted egress, attempt/byte limits and access stops.

## Meaning of a result

- `open`: the official, current, job-bound application page presents supported editable identity fields and a visible enabled application control. The control may be JavaScript-driven without an explicit POST action.
- `closed`: an official closed notice or expired published deadline was established.
- `unverified`: proof is missing, conflicting, expired, blocked, unsupported or the browser runtime failed.
- Existing speculative-pool checks retain their `lead` result.

Every browser result sets `submission_tested: false`. No field is filled, button clicked, form submitted or CAPTCHA solved. An open path is not proof that a submission would succeed, and does not resolve a separate applicant-fit or eligibility gap.

The static validator remains strict about what unrendered HTML can prove. Browser fallback runs only after a successful static HTTP fetch fails to establish a form. Access errors do not trigger a browser retry. Default runs remain static-only.

## Reuse across site types

One capture and deterministic control-checking flow serves small target adapters:

- Lever: exact official board/job route, then its `/apply` route
- Greenhouse: exact official board/job route (available through the provider API; the normal Greenhouse pipeline still prefers its existing official question schema)
- Generic structured postings: exact canonical same-page URL with source-bound description and rendered employer identity

Adding a site adapter means defining its official canonical posting/application identity, not duplicating browser automation or HTTP logic. Redirects, visible embedded frames, cross-origin form targets, missing controls and unsupported layouts remain unverified in this MVP. A separate form action is not required, but an explicit conflicting action or job ID is rejected.

## Runtime and trust boundary

Use an already installed Node runtime, Playwright Core 1.62-compatible package and sandbox-capable Chromium. Python browser packages are unnecessary. The bounded process supervisor currently requires POSIX (Linux/macOS or WSL); native Windows Python is unsupported. No automatic installation, login, persisted browser profile, cookies or credentials are used.

The provider invokes its own worker and validates its private process response. There is no public API accepting a saved/model-written capture JSON as proof. A request nonce, exact target, ephemeral capture context ID, timestamps, source request receipts, rendered HTML SHA-256 and deterministic rendered observations are bound together. Live captures are refreshed on each verification call; synthetic fixture captures cannot mark a job open. This trust assumes the deployment's code, executable/module configuration and local evidence store are trusted; a Python type or hash is not a security boundary against a malicious host process.

Fresh evidence has an explicit expiry (five minutes by default). Expired browser evidence stops satisfying the engine's availability check. Closure, access challenges, incomplete resources, oversized captures, conflicting identities and populated identity fields fail closed.

Only exact deployment-approved resource hosts are fetched. The browser is offline with service workers blocked; requests are fulfilled by Python, redirects rejected before following, and non-GET requests/WebSockets/popups/downloads are blocked. Unavailable CSS or scripts make the capture incomplete rather than pretending the page was verified. Resource hostnames are never added automatically from scraped content.

Playwright normally detaches Chromium into another process group. The isolated worker installs a small spawn guard before loading Playwright to keep its spawned processes in the supervisor's process group. Chromium's sandbox stays enabled. The existing bounded supervisor kills the group on timeout/cancellation; normal completion closes the browser. A real nonbrowser detached-child regression tests the ownership boundary. An opt-in Chromium timeout fixture additionally waits for a real page request, withholds its broker reply, invokes the actual supervisor timeout and asserts the browser process group has stopped. Any unreaped zombie PIDs are reported separately; this is not a claim that init reaped every killed orphan.

Network receipts are retained even when deterministic validation rejects the capture. Interrupted captures recover the latest private progress journal and flag incomplete request accounting. Reported request totals are observed attempts, not a claim that an interrupted request finished.

## Usage

From `engine`, with the existing Python environment and installed Node package resolvable:

```sh
PYTHONPATH=src python -m jobrouter.cli verify --db jobs.sqlite --ids lever:example:abc \
  --browser-host jobs.lever.co --browser-node node --playwright-module playwright-core
```

Named ESM and CommonJS/default exports are supported. If necessary, pass an existing absolute module path with `--playwright-module` and existing Chromium path with `--browser-executable`. Add only independently approved exact resource hosts with additional `--browser-host` arguments. Managed egress hosts still need explicit `--trusted-proxy-host` configuration. Never disable Chromium's sandbox to make a restricted host work.

Python callers can provide `BrowserApplicationVerifier(BrowserPolicy(...))` as `browser_provider` to `run_search` or `verify_application`. This capability is deployment configuration, separate from `ModelRouter` and any job/profile text.

## Tests and current evidence

Ordinary unit tests cover policy, identity, provenance, expiry, synthetic-evidence rejection, JS-button semantics, form controls, conflicts, network receipt accounting and process cleanup. These tests do not establish live job availability.

Opt-in browser fixtures use inline static and delayed JavaScript forms at two site types, plus disabled/hidden controls. Their network is synthetic and never contacts a public site; they test rendering and classification while ensuring fixture receipts cannot qualify real jobs.

```sh
JOBROUTER_BROWSER_TESTS=1 PYTHONPATH=src python -m unittest discover -s tests -p 'test_browser_runtime.py' -v
```

Optional environment settings: `JOBROUTER_NODE`, `JOBROUTER_PLAYWRIGHT_MODULE`, `JOBROUTER_CHROMIUM`.

At implementation time, sandboxed Chromium launch in the cloud shell failed with `socket() failed: Operation not permitted`. That restriction was not bypassed or retried through another browser route. The rendered fixtures are therefore explicitly skipped there. Authorized local QA of published `eae7a5` (tree `742b068f`) passed all four real rendering fixtures and all 166 tests without skips using Node 22.22.3, Playwright Core 1.62.1, Chromium 153 and Python 3.12.3. Normal cleanup left no browser processes or zombies. That QA exposed a CommonJS absolute `index.js` import incompatibility; the minimal named/default-export repair has offline Node regression coverage. The new genuine Chromium timeout fixture and the repaired CommonJS configuration still await authorized local runtime QA. No new live verification or relevance score is claimed.
