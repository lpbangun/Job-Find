# JobFind evaluation preregistration v0.2

Status: DRAFT FOR INDEPENDENT REVIEW. Not approved, not frozen, not executed.
No held-out input was opened to prepare this protocol. All profiles in this
protocol are synthetic. This does not measure fit for the actual user's profile.

## 1. Claim and study arms

The target is at least 90% genuinely relevant recommendations, without padding,
while respecting each brief's hard constraints and delivering useful coverage.
An observed target pass describes this curated cohort only. This study cannot
certify population-level reliability or represent future users.

Compare A, the frozen JobFind engine and its host workflow, against B, a standalone
agent doing public web search. B may plan queries, use synonyms and inspect public
employer/ATS pages, but may not call JobFind or see A's outputs. Both use the same
host model versions, search provider, allowed public tools and browser capability.
Different internal search strategies are allowed. No paid search APIs, private
accounts, applications, candidate-data entry or challenge bypass are allowed.

The earlier six-case development comparison naming Jobsss is historical design,
not a completed JobFind baseline. Do not relabel its runs or combine them with
this study. Do not modify Jobsss to conduct this evaluation.

## 2. Cohorts and frozen input contracts

Use the existing 40 synthetic development briefs D01–D40 unchanged. Preserve their
exact prompts, profile JSON or null, required criteria, preferences, overrides,
expected actions and provenance. D09 and D32 are clarification tests; do not give
them invented answers to obtain jobs. D10 remains a searchable, coherent but
implausible request, not an automatic exclusion from evaluation.

A three-case development pilot requests 30 ranking slots per arm:
- D39: broad profile-led instruction, with its explicit Android/Spain/pay filters
- D38: narrow occupation and institutional source search
- D40: sparse prompt-only search, with no invented candidate profile

This is three lists of up to ten, not a promise of thirty eligible vacancies or
thirty distinct jobs. Cross-brief and cross-arm overlaps are reported. Results
are diagnostic, not independent release evidence. The full 40-case development
run includes the existing six pilots D01, D03, D05, D07, D08 and D38, profile
conflicts, career changes and other role/geography/pay edge cases.

The existing 20 held-out briefs remain sealed. After independent protocol approval,
a custodian who did not implement or tune the engine registers their opaque IDs,
input hashes and split; the implementation worker must not inspect their content.
The custodian prepares criterion sheets before seeing either arm's results and
executes the frozen workflow without adapting it. If the roster cannot establish
at least five opportunity-rich search briefs, plus at least two searchable briefs
in each of profile-led and prompt-only modes, the corresponding release evidence
is insufficient. Do not replace difficult briefs after seeing outputs. A fresh
independently authored sealed extension is required for missing evidence.

For all arms, send byte-identical prompts and identical canonical profile JSON.
Current explicit instructions override saved preferences, not candidate facts.
Hard constraints require prompt/profile provenance; preferences only rank.
No universal salary, location, seniority or applicant-eligibility assumptions.
No profile means assess the requested job characteristics, disclose unassessed
applicant qualifications and never claim personal eligibility. With a profile,
mandatory candidate qualifications must be supported; UNKNOWN is conditional.
Salary thresholds use fixed base or the published lower bound unless the prompt
expressly accepts range overlap. Do not substitute OTE, equity, FTE pay or guessed
annualizations. All remaining interpretations are resolved before results exist.

## 3. Resource-matched execution

Per brief per arm, freeze these ceilings:
- 15 minutes from receipt of inputs, including interpretation and verification
- 20 public search calls, at most 10 hits returned per call
- 120 HTTP attempts, including robots, redirects, failures and browser resources
- 60 distinct candidates selected for detailed extraction/review
- 121 host model calls and 200,000 combined input/output tokens
- At most four concurrent operations; one-second minimum interval per origin
- Zero incremental paid-search spend; no new provider subscriptions

Each category has its own ceiling; unused units do not transfer. Reading search
hits cannot hide full-page retrieval. Tools that cannot expose underlying HTTP
attempts must be excluded from the matched arm or separately labeled as an
unmatched capability study. A deployment-owned wrapper must enforce aggregate
limits across search, direct fetch, browser and model calls before dispatch;
record all reservations, failures, elapsed time and final counts. If exact token
usage or actual served-model identity cannot be recorded, mark the matched study
blocked, not equivalent by assumption. Host subscription access alone is not
proof of zero marginal model cost; record billing basis when known.

Use the same seed URLs (possibly empty), source-host permissions, browser and
search capabilities in each paired run. Freeze them before running the pair;
no hosts are silently added from scraped content. Do not choose job seeds from
one arm's output. Shared cache reads have the same debit as a network retrieval;
record cache age. Caches may not leak one arm's discoveries to the other.

Order briefs by a seeded shuffle (seed 20261010). Alternate A-first/B-first by
position; begin both arms of a pair within one hour and complete the pair on the
same UTC date. No arm sees the other's interim output or feedback. If interruption
prevents completion, keep the case with its original outputs/error and zero yield
where none exist. Do not rerun selectively; a whole paired rerun is a separately
labeled sensitivity analysis. There is one primary held-out run.

Freeze raw outputs and original rank at deadline. No after-the-fact replacement,
reranking, deduplication, constraint relaxation or extra verification by an arm.
Keep qualified recommendations separate from explicitly conditional leads.

## 4. Independent opportunity pool and official evidence

After both outputs are frozen, a neutral researcher, blind to their results,
runs the same 15-minute/20-search/120-HTTP/60-candidate budget on the same input.
Its independently found candidates plus both arms' candidates form the pool.
Preserve source-of-discovery membership, including candidates unique to each arm.
Pool size is a discovered lower bound, never an estimate of all jobs on Earth.
Report both pooled capture and capture of neutral-search-only opportunities.

Verify pooled unique candidates in deterministic canonical-ID order. The common
verification allowance is 60 minutes and 500 HTTP attempts per brief, with the
same source permissions, no applications and no applicant data entry. An exceeded
budget leaves remaining candidates UNKNOWN; never drop them from reporting.
Use the same official-source evidence packet for both judges and both arms.
Record snapshots, hashes, exact quotes, UTC timestamps, official authority, role
ID, hard criteria, and the current application-start path. A 200 page alone is not
proof of acceptance. Challenges, inaccessible dependencies and unsupported forms
remain UNKNOWN; do not disable protections to obtain a passing label.

Verification must finish within 24 hours of both outputs. For the primary
VERIFIED_RELEVANT label, require both sufficient evidence at arm submission and
independent confirmation. Later evidence may establish discovery truth, but cannot
repair an unsupported original recommendation. Record intervening closure or change
separately and provide an explicitly labeled time-change sensitivity analysis.
Do not override the engine's existing five-minute rendered-evidence expiry: record
its validity at submission; independent checking produces its own new timestamp.

## 5. Blinded independent judgments

Use two independent judges who did not implement, tune or produce either arm's
outputs. Humans with relevant occupational knowledge are preferred. An automated
judge must use a separately identified model, isolated context and frozen prompt;
two sessions of the same production model do not establish model independence.
Before holdout execution, record each judge's actual model/version or human role,
the adjudicator and their conflicts. If genuine independence cannot be established,
label results development-only and do not open the holdout.

Assign neutral arm IDs and shuffle candidate cards with seed 20261010. Remove
branding, scores and implementation rationales, preserving substantive claims and
uncertainty labels. Give judges the criterion sheet, candidate qualifications and
shared evidence packet, never the arm identity. URLs may reveal retrieval patterns;
state that residual blinding limitation. Judges cannot search independently outside
the shared evidence budget or alter the brief. Preserve their independent votes
before a third independent adjudicator resolves disagreements with written reasons.
Report raw agreement and Cohen's kappa; undefined kappa remains undefined.

For every mandatory criterion record PASS/FAIL/UNKNOWN plus source quote and
rationale. Score substantive duties/level fit 0–3: wrong, weak/adjacent, substantial,
strong. Score each preference separately YES/NO/UNKNOWN; no preference compensates
for a hard failure. Portfolio simulations are not employment experience.

Labels: VERIFIED_RELEVANT requires role fit >=2, all applicable mandatory criteria
PASS, supported original claims, current official application acceptance, and no
previous duplicate in that arm's list. Otherwise use HARD_MISMATCH, UNVERIFIED,
STALE_OR_INVALID or DUPLICATE; preserve all applicable diagnostic flags even when
one primary label takes precedence. Judge discovery truth and output fidelity
separately so a lucky actual match does not excuse fabricated evidence.

## 6. Metrics and concrete target gates

For each search brief, n is the number of primary recommendations in its original
first ten slots, r is unique VERIFIED_RELEVANT jobs there, and A is independently
confirmed matching vacancies in the pooled reference. Let K=min(10,A). A is
always a discovered lower bound. Separately record reference completeness as
COMPLETE or INCOMPLETE under the gate below; a numeric A alone cannot establish
scarcity or absence.

Report r/n (undefined when n=0), r/10, r, A, r/A when A>0, K-r clipped at zero,
duplicates, every hard failure, unknowns, unsupported claims, stale jobs and costs.
Also report all separately labeled conditional leads and their judgments. Any
job-like claim presented as a match counts as a recommendation regardless of its
heading; genuine clearly unverified leads cannot inflate r or conceal missing slots.
Never promote rank 11 to replace a duplicate or failure. Report every registered
brief, including missing runs, with full denominators and 1/5/9-match coverage.

### Exact estimands

Let S contain every registered searchable brief, including missing/error runs;
clarification briefs are outside S. For a missing run set n=r=0 and separately flag
its operational failure. Preserve raw P_q=r_q/n_q as UNDEFINED when n_q=0,
regardless of A_q. A_q=0 with n_q>0 gives P_q=0, not UNDEFINED; a qualified
recommendation in that case also violates calibrated abstention.

- Raw returned-list macro precision: mean(P_q for q in S with n_q>0). Publish
  both its count of contributing briefs and |S|; UNDEFINED if no contributors.
- Raw returned-list micro precision: sum(r_q over S)/sum(n_q over S), UNDEFINED
  if the denominator is zero. Missing outputs cannot lower this estimand, so it
  is never used without the completion and yield gates.
- Macro strict P10: sum(r_q/10 over S)/|S|, UNDEFINED if S is empty.
- Mean yield: sum(r_q over S)/|S|. Coverage-at-j: count(q in S with r_q>=j)/|S|
  for j=1,5,9; these are UNDEFINED only when S is empty.
- Let F={q in S: reference is COMPLETE and A_q>0}. Define a separate gate score
  G_q=P_q if n_q>0, otherwise 0, for q in F. Opportunity-eligible macro gate
  score is mean(G_q over F), UNDEFINED if F is empty. This zero is a task-delivery
  penalty, not a claim that raw empty-list precision is mathematically zero.
- Reference capture r_q/A_q is reported only for A_q>0, flagged when incomplete;
  a positive lower-bound pool is not total-market recall.

All these observed gates must hold on untouched held-out searchable briefs:
0. Evaluation completeness: every registered arm/case has a completed bounded run,
   immutable output (an explicit empty output is valid), complete request/model
   accounting and required judgments. Missing, crashed, timed-out or error-terminated
   runs fail operational completion even if the other arm finds no opportunities.
   A graceful budget stop may complete an arm's search but never erases its shortfall.
   Reference completeness additionally requires the frozen neutral search procedure
   and shared verification procedure to finish, with no blocked required source,
   unfinished planned search, budget-exhausted pending verification, unresolved
   candidate or unresolved adjudication. A blocked/exhausted/unresolved reference
   is INCOMPLETE: its A cannot certify zero or scarce opportunity. All dependent
   quality/yield outcomes are INSUFFICIENT, even if their numeric lower-bound
   metrics look good. Retain these cases in S and all reports; never drop, replace
   or relabel them as impossible to escape a gate. Whole-study outcome reports
   both operational FAIL flags and evidence INSUFFICIENT flags where applicable.
1. Raw returned verified precision >=90% for every q in F; n=0 fails this per-brief
   gate. Raw overall macro precision, raw overall micro precision and the separate
   opportunity-eligible macro gate score must each be defined and >=90%. No
   undefined metric can pass, and all other gates still apply.
2. Zero known hard-constraint violations and zero unsupported material fit or
   availability claims in qualified outputs, including zero-opportunity briefs.
3. Per q in F, r >= ceil(0.9*K). Thus A>=10 requires at least nine verified
   results; scarce pools with A=1..9 require all available jobs. No padding.
4. At least five held-out briefs have COMPLETE references and A>=10. Report their individual outcomes and
   at least nine-result coverage; if fewer exist, evidence is insufficient rather
   than a pass based only on scarce briefs.
5. Clarification cases all identify the actual missing fact/contradiction, ask a
   focused question and make no fabricated match claim. They receive no job
   precision score and do not enter the searchable-brief yield denominator.

When A=0 and the reference is COMPLETE, report 'no verified eligible jobs found
in the evaluated sources', zero yield and undefined precision for an empty list. Do not infer that no jobs exist
or award a 100% precision pass. Required behavior is calibrated abstention with
search/access receipts and no qualified matches. These cases remain in whole-set
coverage/yield and failure tables but cannot satisfy the minimum rich-cohort gate.
A coherent improbable request remains searchable; a contradiction needing an answer
is scored separately only when its expected action was fixed before results.

### Descriptive resampling only

Resample |S| paired brief clusters with replacement 10,000 times using seed
20261010, retaining both arms and all per-brief flags in each sampled cluster.
Use Python 3.12 `random.Random(20261010)`, lexicographically sorted brief IDs and
`choices(ids, k=len(ids))` once per replicate; record the interpreter version.
Recompute the exact estimands above for each replicate, including their original
rules for n=0 and empty contributing sets. Use linearly interpolated 2.5th and
97.5th percentiles only if all 10,000 replicates define that estimand (sorted
replicate index h=(m-1)*p, linear interpolation between floor(h) and ceil(h)). If any
replicate is undefined, report its count and suppress that estimand's interval
as UNDEFINED; do not discard replicates, substitute values or resample replacements.
Report every raw denominator and zero-return count alongside any interval.

For paired mean yield and strict-P10 differences use all S; for a paired raw
precision difference report mean(P_Aq-P_Bq over J), where
J={q in S: both arms have n_q>0}; report J and all
excluded IDs/reasons, and return UNDEFINED if J is empty. Resample S as above and
recompute J within each replicate, with the same undefined-interval rule. This
complete-output precision comparison cannot replace all-S yield/completion gates.

These percentile intervals describe resampling variability within this fixed,
curated synthetic cohort only. All-perfect observed briefs may produce [1,1];
that degeneracy is not certainty about unobserved briefs or future users. No
bootstrap lower bound, Wilson interval or point estimate from this study may
certify population relevance >=90%. A representative sampling design and separate
prospective validation would be needed for a population claim; neither is part
of this protocol. Do not describe a descriptive interval as statistical release
certification.

For A-versus-B report each paired difference in yield, strict P10 and precision,
win/tie/loss, overlap, costs and all failure categories. Passing absolute quality
does not establish general superiority. Report which arm had higher observed
yield in this cohort and its descriptive paired interval; even an interval wholly
above zero cannot establish superiority for future users.
No comparison to the user's own 30-job shortlist is claimed by the synthetic pilot.

The current `evaluate` helper does not implement these release gates. In particular,
one correct result against a one-job reference may set `all_case_targets_met` true
while strict P10 is 0.1 and requested-count shortfall is nine. That is a
reference-limited metric, not evidence of ten-result delivery. `release_pass`
remains false. A protocol-aware audited report must separately enforce the
opportunity-rich sample, coverage, independence, provenance and uncertainty gates.

## 7. Freeze, audit and stopping rules

A reviewer independent of implementation must approve this protocol in writing
before the holdout custodian reads or releases held-out inputs for execution.
The freeze manifest contains protocol hash, code/tree hashes, all prompts, rubric,
criterion-sheet hashes, cohort hashes, tool/model versions, permissions, budgets,
seed, randomized schedule, judgment identities and data-retention location.
A custodian may hash sealed bytes without exposing their contents to implementers.
Store raw outputs, every tool/model receipt, evidence, two judge votes and any
adjudication keyed by run, blind arm, brief and canonical job ID.

First run the three-case pilot, then the complete development cohort. Fix defects
only against development data. Prove shared-budget enforcement and audit completeness
with synthetic fault tests before freezing. Missing deployment capabilities or
independent judges block holdout execution; they do not authorize weaker controls.
If thresholds or budgets need changing after development, issue a versioned protocol
and secure a new independent review before opening any holdout.

After holdout inspection, no tuning against it. Failed, blocked and insufficient
outcomes are published in the evaluation report as such, not erased. Further fixes
require a fresh sealed cohort for a new primary test. This protocol does not itself
authorize publishing, deployment, private-profile transmission or a release claim.
