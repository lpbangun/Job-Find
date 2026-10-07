# CLI and JSON contract (v1)

## Commands

Python 3.10+, stdlib only; Linux/macOS (`fcntl`, process groups and fork enforce locks/timeouts).

```text
python scripts/sourcing.py init --run DIR --brief FILE [--requests INT] [--seconds NUMBER] [--out FILE]
python scripts/sourcing.py status --run DIR [--out FILE]
python scripts/sourcing.py action --run DIR --file FILE [--out FILE]
python scripts/sourcing.py search --run DIR --query STRING [--limit INT] [--out FILE]
python scripts/sourcing.py fetch --run DIR --url URL [--out FILE]
python scripts/sourcing.py submit --run DIR --file FILE [--out FILE]
python scripts/sourcing.py validate --run DIR [--out FILE]
python scripts/sourcing.py results --run DIR [--out FILE]
```

`init`, `action`, `submit` accept `-` as the input filename to read a single JSON object from stdin. All commands print a single JSON value to stdout. `--out` additionally writes that value to an explicit file using atomic replacement (parent directories created); it cannot replace the run's `state.json` or `.lock`. Do not point output at input/source files. Exit 0 means the command persisted/output a result, **not** that a search or fetch succeeded. Inspect receipt `status` (`ok`, `error`, `pending`, or `redirect`). Exit 2 signals invalid command/input, unavailable run, or exhausted deadline/request allowance; handled errors print `{"error":"..."}`. Argparse syntax errors print usage on stderr. `validate` and `results` are aliases and revalidate against current freshness; neither performs network calls. `status` reads the full durable store. There is no separate resume command: continue using the same `--run` directory.

`init --requests/--seconds` overrides those fields before freezing the effective brief. No command can extend/reset an existing run. Bounds are limits, not costs or promises of yield. `search --limit` defaults to 5, allowed 1..100; bridge responses exceeding it fail. Query maximum is 4096 characters.

All commands also accept `--compact`. This output-only projection omits `raw_body`, `raw_base64` and the duplicate `posting.description`; it retains quoteable `text`, identity, hashes and refs. It applies to stdout and `--out`, never the authoritative store. Prefer compact fetch/status evidence for host interpretation; full status/raw capture remains available for source links and missing context.

## Brief

Illustrative prompt-only request; not a benchmark result:

```json
{
  "mode": "prompt_only",
  "requested_count": 5,
  "hard_constraints": [
    {"id": "geography", "description": "Singapore SWE role", "mandatory": true},
    {"id": "salary", "description": "SGD 120000+ annual base salary", "mandatory": true},
    {"id": "level", "description": "Suitable for 3 years relevant experience", "mandatory": true}
  ],
  "preferences": ["big tech", "frontier AI labs"],
  "limits": {
    "requests": 30,
    "seconds": 600,
    "timeout": 15,
    "max_bytes": 2000000,
    "freshness_seconds": 86400
  }
}
```

Required: mode `prompt_only|resume|profile`, positive integer requested count, constraints array with unique nonempty string `id`, preferences array, and limits with finite positive numbers. Constraint descriptions are text; mandatory defaults true and must be boolean when supplied. Requests and max_bytes must be integers. Hard constraints are host-interpreted descriptions, not a lexical query parser. Preferences should be strings; structured values are not recommended. Unknown Singapore sponsorship is not a hard gate unless the user actually requested that gate.

For profile/resume mode include `profile_text` containing unchanged authorized proof text; its exact passages are the ranking authority. Keep separately dated preference/resume provenance in additional brief fields as needed. Missing profile proofs cannot yield qualified personal-fit recommendations. Core never reads saved profiles or changes them. File intake/interpretation belongs to the existing host, which embeds effective text before init.

Optional history:

```json
{
  "application_history_file": "history.json",
  "exclude_history_matches": true
}
```

Merge these into the brief. `application_history_file` is absolute or relative to **the run directory**, snapshotted at init. Alternatively `application_history` is an inline array. A supplied file takes precedence over the inline array. File format: JSON array of `{url?, company?, title?, ...}` records. Parent/host selects relevant actual application records (not saved-only leads). URLs are normalized exactly; invalid URLs fail initialization. The snapshot remains stable if the source file later changes. Exact canonical URL match is `exact_url_match`; same stripped/casefolded company and title but no matching URL is `needs_review`, never an identity merge. With exclude_history_matches true, exact qualified matches become excluded and collisions/unavailable history become conditional. A nonmatch is only `not_found_in_available_records`; no universal never-applied assertion.

## Trusted host search bridge

`SOURCING_SEARCH_COMMAND` is parsed with `shlex.split` and executed **without a shell**. It receives:

```json
{"query":"public-safe query","limit":5}
```

It must print exactly one UTF-8 JSON object (no debug logs on stdout):

```json
{"backend":"host-backend-name","results":[{"url":"https://example.org/role","title":"Example discovery title","description":"Discovery snippet, not verified role evidence"}]}
```

Metadata beyond these fields may be provided but is not relied on. No provider SDK belongs in the core. Bridge timeout and stdout byte cap are enforced; stderr is discarded, process group is killed on completion/failure. Bridge authors must honor one bounded search request without hidden retries/fan-out and obey provider access terms. The runtime caps adapter invocations, not invisible provider HTTP subrequests or monetary charges. Unavailable/malformed/oversized/failed bridges produce error receipts and consume budget. Secrets never belong in query text or command-line arguments.

## Fetch receipts

Each attempt reserves one request under a file lock **before** DNS/HTTP; every redirect reserves another. Failed/unsafe requests consume the allowance too. The whole redirect traversal shares a per-operation timeout, bounded by the remaining run duration. Six fetched hops maximum, subject to the aggregate request budget. DNS and actual wire operations run in bounded child processes; pinned approved IPs prevent re-resolution between validation and connection. TLS verifies the original host. Local/private/reserved resolution (including any private result among mixed answers), credentials, non-HTTP(S), unusual ports and unsafe URL characters are denied before transport. There are no automatic retries or browser/challenge bypasses.

Successful evidence contains `id`, `run_id`, `started_at`, `captured_at` (Unix UTC seconds), `requested_url`, canonical final `url`, `http_status`, `headers`, `bytes`, raw-byte `sha256`, exact `raw_base64`, decoded UTF-8 `raw_body`, extracted `text`, and `text_sha256`. JSON is parsed/reformatted; HTML script/style text is omitted. Quote exact extracted text (or explicitly `representation: raw` for an observed raw-source link). HTML attributes often require inspecting raw_body. Compressed/oversized/incomplete responses fail closed. No status is automatically interpreted as open or closed. Simple extraction does not render JS; unavailable evidence remains unverifiable.

HTML intake tries standard `application/ld+json` JobPosting objects (including arrays, `@graph`, array-valued `@type`) before visible fallback. All metadata blocks participate in selection: exactly one explicit canonical URL match wins; otherwise only a lone posting without a supplied URL may use `page_url_inferred`. Relative URLs resolve against the fetched page. Existing canonical rules remove only fragments, utm_*, fbclid/gclid; other query fields remain significant (including `source=GoogleJobs`). Multiple matches, ambiguous URL-less postings and explicit mismatches do not contribute metadata identity/description. Malformed JSON/field types fall back safely. Selected descriptions retain heading/list boundaries and bounded entity decoding; `text` contains only selected title/company/description, not neighboring metadata. Raw body remains exact, including other metadata; do not quote it to borrow another job's requirements. Visible fallback preserves text; the explicit `Job Application for TITLE at COMPANY` page-title pattern may provide provisional identity only when no rejected/ambiguous posting metadata exists. Fallback is not a generic title/company guessing algorithm.

Recognized intake exposes `posting: {title, company, description, source, binding, url, caveat}`. A successful fetch with recognized identity and no existing candidate at its canonical final URL also creates a `provisional:true` candidate in the **same locked/fsynced state transaction** as the receipt. It includes source-backed identity refs, `availability:unverifiable`, empty acceptance evidence/fit dimensions, and every brief constraint as unknown. `candidate_id` links the receipt to this checkpoint (or to an existing candidate). No metadata/HTTP success/redirect automatically proves open or closed. No named checkpoint is fabricated for unsupported/mismatched/ambiguous intake. Re-fetch keeps any existing candidate unchanged, including provisional ones, to avoid silently replacing richer host assessment; host must explicitly submit revised evidence after review. Final URL is the checkpoint identity after redirects, not the original role URL. Captures and candidates persist after request/deadline exhaustion; status/results need no retrieval budget.

The bounded entity-decoding and structural normalization approach is adapted conceptually to Python stdlib from JobSSS `src/discovery.js` (MIT), https://github.com/lpbangun/jobsss at `9a8e95a0cbd4bb800691bb437cefbad0b145c665`; no transport/scoring/orchestration code is ported. Availability and source-binding behavior intentionally remain stricter.

Use `fetch` for any observed public API URL, not only ATS URLs. Its receipt cannot support a different role merely because the response mentions it somewhere. The source-binding gate below handles a concrete linked JSON posting.

## Candidate

Illustrative shape; substitute actual captured receipt IDs and passages, not the placeholders:

```json
{
  "company": "Example Employer",
  "title": "Software Engineer",
  "url": "https://example.org/jobs/observed-posting",
  "kind": "vacancy",
  "availability": "open",
  "evidence_refs": ["ACTUAL_RECEIPT_ID"],
  "identity": {
    "company": {"ref":"ACTUAL_RECEIPT_ID","passage":"Example Employer"},
    "title": {"ref":"ACTUAL_RECEIPT_ID","passage":"Software Engineer"}
  },
  "availability_evidence": [
    {"ref":"ACTUAL_RECEIPT_ID","passage":"EXACT CURRENT ROLE ACCEPTANCE PASSAGE"}
  ],
  "hard_findings": [
    {"id":"geography","status":"pass","ref":"ACTUAL_RECEIPT_ID","passage":"Singapore"},
    {"id":"salary","status":"unknown"},
    {"id":"level","status":"unknown"}
  ],
  "fit_dimensions": [
    {"name":"employer preference","score":75,
     "criterion_passage":"frontier AI labs",
     "job":{"ref":"ACTUAL_RECEIPT_ID","passage":"EXACT RELEVANT JOB PASSAGE"}}
  ]
}
```

`kind` is vacancy, invitation or lead; `availability` open, closed or unverifiable. HTTP 200 without explicit host-interpreted current acceptance evidence cannot pass. Host must identify rendered not-found/generic pages and employer authority, not quote any arbitrary page phrase as an availability claim. Open/closed each need supporting passages. A failed URL is never a closure fact. A lead may have unverifiable availability and appear in the unverifiable bucket; only structurally supported invitations/leads with an interpreted status appear in leads, still never in vacancy counts.

`hard_findings`: one finding per brief constraint, pass/fail/unknown; omitted becomes unknown. Pass/fail require exact quote/ref; duplicate/unknown IDs invalidate. Optional (`mandatory:false`) findings never disqualify but remain visible. Mandatory fail excludes without requiring a fit grade; mandatory unknown is conditional. Invalid evidence makes a record unverifiable rather than an evidence-backed exclusion.

Every scored fit dimension needs `name`, finite numeric score 0..100 and a job quote. For resume/profile, use `profile_passage` copied exactly from profile_text instead of criterion_passage. For prompt-only, criterion_passage must be copied from the brief's preferences or constraint descriptions; profile_passage is forbidden. Missing/nonfinite grades make otherwise-open candidates unverifiable; NaN/Infinity are retained as JSON null for safe inspection. Equal-weight arithmetic mean is the ranking rubric; choose consistent dimensions across candidates. Meaning and score calibration remain host judgments.

Optional `posting_provider` plus `posting_id` dedupes by exact company/provider/posting ID. Otherwise dedupe exact canonical URL, preserving role-significant paths/query fields and removing fragments, utm_*, fbclid/gclid only. Same company/title alone never merges distinct roles. Resubmission replaces the current candidate at the same identity; append-only events preserve disposition timing, not full revision bodies. Persist candidates early rather than waiting to fill the quota.

### Explicit linked JSON source binding

For evidence from a public API whose URL differs from candidate.url:

1. Capture candidate.url and an explicitly observed source URL with separate fetch commands.
2. Include both receipt IDs in evidence_refs and `posting_id` (exact string/value from JSON).
3. Supply `source_links: [{ref: "CANONICAL_RECEIPT_ID", passage: "EXACT_API_URL", representation: "raw"}]` when the URL appears only in raw HTML. The canonical receipt must actually contain that exact source URL; the runtime does not infer endpoints from employer/ATS names.
4. API JSON must contain an object with an exact `id|jobId|postingId` equal to posting_id **and** an exact `url|jobUrl|canonicalUrl` equal to candidate.url. Validation searches nested arrays/objects for this record, then scopes **all** quotes from that API receipt to that object. Other jobs in the same board response cannot lend their salary/location/benefits to the candidate. Company identity may cite the original canonical receipt if it is outside the API posting object.

No matching record or observed link means unverifiable. This gate intentionally does not support arbitrary unlinked policy pages or opaque API shapes. Change an adapter/gate only for an exercised, separately tested requirement; don't relax it to force qualification.

## Durable state and outputs

Run files: `.lock` plus atomically replaced/fsynced `state.json`. State contains immutable effective brief/history, run ID, creation time, request count, evidence/search maps, actions, candidates and events. Treat it as private trusted storage; no cryptographic protection from a malicious local writer. Store it on a local filesystem with working POSIX flock/atomic rename semantics. Crash after reservation leaves pending receipt and consumed request: never refund, reset or replay automatically. Shared workers must use the same run. No worker may fetch externally outside these commands; a host tool policy is needed to make that boundary adversarially enforced.

Output `version:1` has complete arrays `qualified`, `conditional`, `unverifiable`, `excluded`, `leads`; `counts`, ranked `shortlist` (up to requested_count qualified), `requested_count`, `used_requests`, limits and caveat. Each assessment carries score/null, hard findings, history status, group/reasons and validated_at. Scores sort descending, stable ID breaks ties. Qualified means passed structural gates under host interpretation, not an independently certified truth. Full evidence and exploration frontier are read via status. Every final validation uses authoritative capture times; stale/future/cross-run/bad-hash receipts fail.

Handoff is this versioned CLI/file contract. Optional application-management consumers should import only human-selected records under their own authority. No MCP server or application submission exists here.
