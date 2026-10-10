# Release gates

This is a standalone search service. It does not modify Jobsss or submit applications.
Development takes place in the assistant's workspace, not the user's Windows computer.

## Quality gate (not yet attained)
- At least 90% genuinely relevant top-10 recommendations per feasible held-out brief and overall.
- At least 60 varied briefs, including 20 held out from implementation tuning.
- Independent human or model judgments with explicit job evidence. Self-labeled fixtures are regression tests, not evidence of real-world relevance.
- No known hard-constraint violations in qualified results. Unknown critical criteria remain conditional.
- Reference opportunity coverage and result count prevent abstention from gaming precision.
- Test profile-based, prompt-only, contradictory, sparse, geographically restricted and impossible briefs.
- Current official application paths and timestamps required for live recommendations; a 200 response alone is insufficient.

## Operational gates
- Every request, redirect, failure, source and decision has a receipt.
- Bounded, concurrent frontier; per-origin pacing; no challenge/access restriction bypass.
- Discovery does not require paid search APIs. Optional model execution is supplied by the host; no provider credential is bundled.
- Public job data and private applicant data are kept separate.
- Record actual model identity and failures, not only requested routing labels.
- No monetization-ready claim until security, tenancy, source-use rights and held-out live evaluation have passed.

## Before opening held-out inputs

The gates above are requirements, not a recorded passing evaluation. The following
protocol must be recorded and frozen before the held-out set is opened:

1. Pin the source tree, configuration, model routing and evaluator versions.
   Record actual served-model provenance or explicitly mark it unavailable.
2. Register all 60 or more brief IDs and their development/held-out split without
   exposing the 20 or more held-out briefs to implementation tuning. Record
   predeclared handling of impossible and sparse-opportunity briefs.
3. Fix identical baseline/engine request, candidate, time and monetary budgets,
   source-use rules, evaluation window, result depth and tie/deduplication rules.
   Define the separate requested 30-role comparison, including its denominator,
   baseline and sampling procedure; it is not interchangeable with 60 briefs.
4. Define relevance and hard-constraint rubrics, independent blinded judgments,
   source evidence requirements, disagreement adjudication, reference-opportunity
   coverage measurement, minimum yield and uncertainty reporting. Concrete proposed
   thresholds and the protocol are in [EVALUATION-PREREGISTRATION.md](EVALUATION-PREREGISTRATION.md);
   independent approval and a recorded freeze are still required before holdout access.
5. Record every registered case, including errors, blocked access, missing
   results and abstentions. Preserve unverified application checks as unverified.
   Apply the same handling to the baseline. Missing runs must not disappear from
   the denominator. Keep result precision, strict precision at k, recall, coverage,
   duplicates and shortfall separate.
6. Keep applicant data local unless the exact external transmission is authorized.
   Development may use synthetic profiles; their tests do not establish actual
   user-profile relevance or fulfill a real-profile evaluation requirement.

`jobrouter.evaluation.evaluate` is a metric helper, not a release certifier. It
includes every case present in either supplied mapping, treating missing runs as
empty results, and always returns `release_pass: false`. Callers must supply the
complete registered reference roster: the helper cannot detect a case omitted
from both mappings or certify independent judgments, coverage, live availability,
sample size or lack of benchmark contamination. Empty reference sets do not prove
that a brief is impossible. A separate reviewed evaluation report is required.

Any tuning after held-out results are inspected must be disclosed and evaluated
on a fresh, untouched holdout before a release claim. Fixture/regression passes
and selected-source development smoke results must remain separately labeled.
