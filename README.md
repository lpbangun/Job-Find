# Bounded job sourcing POC

An executable **stdlib Python runtime plus an agent skill**, independent of any job index, profile manager, model provider or application tool. The existing host interprets natural language and evidence; the runtime owns durable runs, atomic aggregate request limits, safe public fetching, exact evidence checks, canonical identity and ranked outputs. No custom agent harness or MCP implementation.

`BRIEF.md` is the preserved historical staging brief. The authorized implementation lives in `SKILL.md`, `references/`, `scripts/sourcing.py` and `tests/`.

## Run

Python 3.10+ on Linux/macOS. No installs. Read [SKILL.md](SKILL.md) for the complete two-path sourcing method and [references/contract.md](references/contract.md) for exact inputs/outputs.

```text
python scripts/sourcing.py init --run runs/my-search --brief brief.json
python scripts/sourcing.py status --run runs/my-search
python scripts/sourcing.py action --run runs/my-search --file action.json
python scripts/sourcing.py search --run runs/my-search --query "public-safe query" --limit 5
python scripts/sourcing.py fetch --run runs/my-search --url https://employer.example/observed-role
python scripts/sourcing.py submit --run runs/my-search --file candidate.json
python scripts/sourcing.py validate --run runs/my-search --out runs/my-search/results.json
python scripts/sourcing.py results --run runs/my-search --out runs/my-search/results.json
```

`--out FILE` is available on every command. Init additionally accepts `--requests INT --seconds NUMBER` to override brief limits before freezing the run. Init/action/submit accept `-` as the input path for stdin. Continue the same `--run` after interruption; re-init is rejected. Every command prints JSON; inspect receipt status even when exit is 0. Syntax/input/budget errors exit 2.

### Minimal brief

```json
{
  "mode": "prompt_only",
  "requested_count": 1,
  "hard_constraints": [{"id":"geo","description":"Singapore","mandatory":true}],
  "preferences": ["software engineering"],
  "limits": {"requests":20,"seconds":300,"timeout":10,"max_bytes":2000000,"freshness_seconds":86400}
}
```

Modes: prompt_only, profile, resume. Profile/resume add immutable `profile_text`; no saved profile is required. Application history is optional JSON-array file or inline records, snapshotted at init. Enable `exclude_history_matches` when requesting roles not in available application records. Exact URL match excludes; company/title collision needs review; no claim of globally never applied.

### Search bridge

Optional `SOURCING_SEARCH_COMMAND` points to a host-owned executable, parsed without a shell. It reads `{"query":"...","limit":5}` on stdin and emits `{"backend":"...","results":[{"url":"...","title":"...","description":"..."}]}` on stdout. Runtime bounds invocations, output bytes and timeout; bridge must avoid hidden retries/fan-out. No provider dependency or live search bridge is bundled. Missing search capability returns a durable error receipt; permitted already-observed URL sourcing still works.

## Guarantees and limits

- Flock plus atomic/fsynced state replacement reserves requests before dispatch. Search/fetch attempts, failures, redirects, retries and verification share one count and elapsed-time window.
- Fetch permits only public HTTP(S), checks every resolution/redirect, pins the approved IP, authenticates TLS, caps bytes and bounds DNS/wire execution. Raw bytes/base64, decoded raw body, extracted HTML/JSON text, hashes and runtime timestamps are preserved. Failed/incomplete access is unverifiable, never closed.
- Standard JobPosting JSON-LD-first intake preserves description headings/lists and selects only unambiguous URL-bound metadata. A lone URL-less posting carries an inference caveat. Recognized identity checkpoints a provisional candidate atomically with its receipt: availability unverifiable, gates unknown, no fit claim. Re-fetch never overwrites a richer host submission. Use `fetch --compact` / `status --compact` to inspect quoteable evidence without bulk raw/base64; full evidence stays durable. See the contract for supported visible fallback and mismatch handling.
- Candidate validation reads captured evidence. It enforces exact quote presence, company/title identity, canonical/source binding, freshness/run ownership and finite scores. Linked public JSON APIs must bind exact posting ID plus canonical URL in one posting object; quotes cannot bleed across jobs.
- Qualified, conditional, unverifiable, excluded and leads stay separate. Requested count is a ceiling on the ranked qualified shortlist, not a fill quota. Mandatory unknown stays conditional; failure excludes; invitations do not become vacancies.
- **Core cannot prove semantic truth**, employer authority or arbitrary prose interpretation. The host must establish current role acceptance; HTTP 200 alone cannot establish availability. Scores are proof-linked host rubric grades, not hiring probabilities. Best means best among examined eligible opportunities, not globally best or hidden jobs guaranteed.
- Local store/bridge/host are trusted. This is not an OS sandbox or monetary-cost firewall; host tools must prevent bypassing the budgeted retrieval boundary. POSIX local-file semantics are required. No automatic applications, outreach, secrets, CAPTCHA/paywall bypass or private-channel access.

## Offline verification

```text
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
python scripts/sourcing.py --help
```

Tests exercise real persistence and subprocess CLI/bridge contracts with injected DNS/wire fixtures; no external service, job search, install or secret is used. Vertical red/green build logs live outside the repository in the requested evidence directory. The suite covers resume/proof grounding, prompt-only ranking, receipt safety/freshness, exact history matching/collisions, canonical duplicates, concurrent reservations, request/deadline exhaustion, redirects/not-found behavior, malformed scores, fetch timeouts/incomplete bodies, raw capture and per-posting JSON scope.
