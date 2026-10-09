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
