# Source pathways and frontier discipline

The host selects sources relevant to the occupation. These are recipes and seeds, not registered live integrations or a coverage ceiling. Change title aliases, problem vocabulary and employer hypotheses when moving between SWE, learning design, FDE or another family.

| Path | Entry | Follow observed relationships | Promotion limit |
|---|---|---|---|
| A role/source | Role aliases + explicit geography/pay | Search → specialist board → employer/ATS → posting | Search snippet is only discovery |
| A source expansion | Source/class missing from coverage | Search for niche association, regional board, newsletter or hiring thread | Permission and reachable canonical evidence required |
| B capability/problem | Supplied resume artifacts and demonstrated work | Capability → problem → implementation ecosystem → responsible employers → hiring | Capability does not imply professional tenure |
| B prompt-only problem | Explicit desired role and criteria | Role/problem hypothesis → product ecosystem → employers → actual openings | Hypothesis is not applicant proof |
| B ecosystem | Public partner directory, project, conference or case study | Organization → observed careers link → vacancy or invitation | Membership or sponsorship is not hiring |
| B business event | Launch, expansion, contract or funding | Demand hypothesis → employer → explicit hiring evidence | Weak signals never accumulate into a vacancy |
| Complementary community | Permitted employer-authored hiring thread/newsletter | Author and date → role/acceptance route → specific role | General invitation stays invitation; inaccessible channels are gaps |

Prefer employer canonical careers/ATS links and documented public feeds. Greenhouse, Lever and Ashby are possible source classes, not a dependency or permission grant. An API token must be observed and employer identity established; don't guess a token from the employer name. A GJI-style index can accelerate discovery but cannot replace standalone sources or fresh validation. Never access LinkedIn through unofficial scrapers or borrow cookies for private channels.

## Choosing the next action

1. Resolve credible candidate evidence gaps likely to change qualification.
2. Follow novel employers in profile-relevant ecosystems and undercovered occupations/geographies.
3. Spend the declared exploratory reserve on new source classes and unfamiliar employers, not repeated variants of the same query.
4. Penalize duplicates, blocked sources and failures. At most one justified alternative route after a block; never bypass a CAPTCHA or paywall.
5. Stop before aggregate budget/deadline exhaustion prevents useful delivery; retain unresolved candidates rather than force a result count.

Action JSON fields: required `target`, `pathway` and `reason`; optional `id` for update, `parent`, `state` (pending/active/done/blocked/exhausted), `expected_evidence`, `evidence_refs`, `relationship` (observed/inferred), `attempts` and `stopping_reason`. Arbitrary descriptive fields are persisted, not executable instructions. Runtime events provide actual request timestamps; host `attempts` is descriptive and must not replace budget accounting.

Keep rationale concise, not hidden chain-of-thought. On resume use pending/blocked state and captured receipts; do not retry every pending request blindly. Finish with explored, blocked, untried and exhausted pathway coverage, plus the strongest next steps if the user authorizes another run. A new run is a new budget agreement, not an automatic retry loophole.

## Optional review and portability

The same existing host interprets evidence and assigns proof-backed grades. No custom agent harness, recursive agents, required second model or profile manager. An independently authorized reviewer can audit meanings and scoring; label it independent only when it actually is. Use JSON output and captured evidence to hand selected records to any downstream application tool. Preserve downstream ownership: this runtime never attests application, sends outreach or stores competing private application state.
