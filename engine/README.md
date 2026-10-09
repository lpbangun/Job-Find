# JobRouter — standalone job-discovery prototype

Work in progress, built separately from Jobsss. This is an evidence-first Python search engine with public ATS collection and a host-supplied model boundary. It does not submit applications or send outreach.

## Current status (2026-10-09)

- 44 offline regression tests pass, including a fixture-driven complete mission.
- Live collection exercised Greenhouse (18 VTS), Lever (39 360Learning) and Workable (6 Hugging Face) using a managed egress proxy. These 63 listings are collection evidence, not 63 relevant recommendations.
- Two VTS application schemas were checked live, read-only. They are not fresh recommendations for the original user.
- Ashby API verification stopped at an HTTP 401 robots response; it was not bypassed. Recruitee remains fixture-only.
- No real host-model run, held-out relevance score, commercial/security review or production readiness claim yet.
- The 90% genuine-relevance release gate has NOT been met. See `docs/ACCEPTANCE.md`.

## Run

Requires Python 3.11+. No external runtime dependencies.

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m jobrouter.cli collect https://job-boards.greenhouse.io/example --db jobs.sqlite
PYTHONPATH=src python -m jobrouter.cli rank --db jobs.sqlite --brief brief.json
```

The CLI `collect` command does not need a model. `rank` without reviewed evidence emits conditional/excluded candidates, never pretends a title score is a verified fit. The Python `run_search` API composes interpretation, collection, deduplication, extraction, independent relevance review and read-only application verification.

## Model routing

The hosting agent/runtime supplies `ModelRouter(callback=...)` or an explicitly configured command (argv, no shell). Planner/reviewer route to a stronger tier; extraction to a faster tier. Requested tier and actual reported model are recorded separately. This project does not bundle API keys or assume a particular subscription exposes an API. Missing runtime support is a blocked stage.

## Source access

Public HTTPS only. Per-origin pacing, request-attempt budget, bounded response size, no automatic retries, robots policy and explicit access/rate-limit stops. Direct transport pins a validated public DNS address while preserving TLS hostname verification. In managed environments with a trusted egress proxy, exact public hostnames must be explicitly allowlisted by deployment configuration; scraped content cannot expand that list.

The frontier follows career/ATS/directory leads from input seeds, with configurable depth and source budgets. It does not yet implement exhaustive web discovery or an unrestricted global search service. Model-assisted frontier expansion, additional adapters and independent coverage evaluation are still in progress.

## Evidence and privacy

SQLite public storage contains source/job evidence, not applicant profiles. The caller owns private prompts/profiles and prior-application history. Relevance reviews bind to the job, brief digest and source digest. Quotes must exist in the retrieved description. Quotation matching is not a guarantee of semantic entailment; independent held-out review remains necessary.

External job descriptions remain their owners' content. Raw live runs and reference clones are excluded from Git. Source references: `lpbangun/oh-shi` and `lpbangun/Job-Find` were inspected; neither is a production dependency. No changes were made to those repositories.
