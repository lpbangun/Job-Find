# Synthetic development harness checkpoint

This is a partial, offline-tested checkpoint. No live paired evaluation was run.
No held-out inputs were opened. Protocol design approval does not approve a release
or establish that execution prerequisites are available.

## Implemented

`EvaluationBudget` is an opt-in thread-safe, mission-lifetime reservation ledger.
Pass the same instance as `shared_budget` to the existing `ModelRouter`,
`PublicFetcher` and (when used) `BrowserApplicationVerifier`. `run_search` rejects
mixed/missing ledger instances before dispatch if any component opts in. Existing
callers without a ledger retain their existing behavior and are not protocol runs.

- Fetchers reserve each HTTP attempt before wire dispatch, including robots,
  failures and redirects, across all participating fetcher instances.
- Routers reserve model calls before dispatch across participating router instances.
- The pipeline reserves candidate reviews before extraction.
- A browser capture reserves its entire worker HTTP request allowance before
  spawning. The child retains its existing request cap. Unused browser allowances
  are not refunded, even after success; incomplete captures cannot release an
  unknown number of spent requests. These are conservative reservation counts,
  not observed attempt totals. Report both separately when actual receipts exist.
- A monotonic mission deadline rejects new reservations; atomic multi-resource
  reservations either debit every counter or debit none. Rejections have ledger
  events. Failed requests retain their reserved units. Snapshots are deep copies.

This ledger lives in one trusted Python process. Browser children receive bounded
pre-reserved allowances, not a live shared ledger. It is not crash-durable and
cannot police a malicious host, unrelated processes or bypassing tool calls.
Snapshot it into the private audit artifacts; it contains counters and operation
names, not applicant profiles or job-page text.

`validate_development_manifest` checks synthetic-only development split, D01–D40
IDs, paired arm names, SHA-256 fields, actual-model declarations, exact protocol
ceilings and capability-evidence references. It refuses held-out/private-profile
runs. This validates structure and declarations, not the truth or contents of
referenced evidence. Passing it with fixture values is not permission to execute
or evidence of model identity; an independent reviewer must inspect real artifacts.

## Exact blockers before any live protocol run

1. No bundled standalone baseline/public search adapter exposes and enforces the
   required shared search/HTTP accounting. Existing callback smoke runs are not a
   matched baseline. No paid search API or substitute source is authorized here.
2. Existing model callbacks reported served identity as unknown. A supported host
   must expose actual version/provenance, input/output token usage and an enforceable
   per-call total-token cap before aggregate token reservations can be implemented.
   Current shared ledger integration enforces model-call counts, not model tokens.
3. Component semaphores and per-origin pacing are still local to components. A
   shared four-operation limit and cross-fetcher/browser origin pacing are needed.
4. The shared deadline prevents new dispatch only; it does not interrupt in-flight
   callbacks. Existing process adapters have their own deadlines. A parent mission
   supervisor must enforce the common deadline and preserve interrupted receipts.
5. Search-call reservations have a generic ledger primitive but no connected search
   adapter. No complete paired executor, durable manifest/evidence exporter,
   evidence-hash verifier or protocol-aware release gate aggregator is implemented.
6. Independent judging identities and holdout custodian are not yet assigned.

Consequently, do not set all manifest capability flags true or claim an executable
paired benchmark from these tests. The next safe checkpoint is a supported host
capability audit and offline adapter tests. No external call is needed to establish
these gaps, and this checkpoint made none.

## Verification

The `test_evaluation_budget.py` fixtures exercise concurrent reservations, atomic
multi-counter denial, robots/failure accounting across fetchers, cross-router
model limits, conservative browser reservations, no-dispatch after deadline,
pipeline wiring, immutable snapshots and fail-closed manifest validation. All
wire/model/browser responses are synthetic; browser processes are mocked here.
They do not establish live availability, genuine relevance or browser safety.
