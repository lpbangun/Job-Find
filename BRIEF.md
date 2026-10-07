# Job Sourcing POC — staged for discussion

Status: STAGED / NOT STARTED. Owner requested a separate project for further discussion, not implementation. No agents, goal loops, collection, installation or deployment are authorized by this staging step. Wait for explicit owner authorization before implementation. Name and design are provisional.

## Hypothesis
A portable agent-driven sourcing skill with small deterministic helpers may find suitable opportunities better than a catch-all hosted inventory. Reproduce the method and evidence, not promise identical results from a changing internet.

## Owner requirements to discuss
- Natural-language search is an explicit acceptance criterion, not simply a sentence passed to keyword search.
- Find roles fitting the user's preferences, with evidence-backed US/remote eligibility and honest unknowns.
- Discover both canonical job-board postings and off-board hiring leads; do not count leads as verified vacancies.
- Check whether postings are still live and report checked-at time, evidence and open/closed/unverifiable status.
- Make source pathways and the pipeline usable by other agents, with explicit host prerequisites.

## Proposed shape — not approved architecture
User request -> structured search brief -> query/title aliases -> permitted source discovery -> bounded collection -> normalization/deduplication -> eligibility and availability verification -> ranked evidence-backed shortlist.

Skill owns workflow and source recipes. The user's agent owns natural-language interpretation and judgment. Small shared helpers own reliable fetching, normalization and evidence receipts. JobSSS remains the private profile/application workspace and optional downstream consumer. The existing General Jobs Index is an optional source, not a required backend. Do not duplicate JobSSS or modify it under this POC without separate approval.

## Reference
https://github.com/lpbangun/jobsss
README.md and TECHNICAL.md on GitHub were inspected during the preceding discussion; this is not runtime certification or a pinned dependency.

Existing inventory: https://general-jobs-index.lpbangun.workers.dev/
Separate checkout: /home/logani/projects/general-jobs-index-worktrees/autonomous-discovery
Its narrow usability goal completed, but inventory growth remains unmet. The latest read-only observation in the preceding discussion reported 2,351 stored-open records and zero fresh records, automation stopped. These are historical observations, not POC results. Latest immediate inventory milestone discussed was 2,500+; earlier 25K remains unmet. Neither is automatically a sourcing-POC acceptance criterion.

## Boundaries for later scope agreement
- No universal scraping promise; permitted public ATS/API/feed/page access only, bounded by host capabilities and source terms.
- No CAPTCHA/paywall bypass, credential borrowing, auto-application or message sending.
- Preserve private profile ownership; do not publish personal data to the inventory.
- Failed/truncated/blocked fetches mean stale or unverifiable, not mass closure.
- HTTP 200 alone is not proof a vacancy remains open.
- No new paid services or paid lookups without explicit budget agreement.
- Preserve deployed index and existing projects; this staging creates no production changes.

## Questions for discussion before any launch
- Skill-only POC versus skill plus bundled helper runtime; CLI/MCP needs.
- First supported hosts and public source pathways.
- Whether natural-language support is agent-only or also required in a website search box.
- Eligibility and off-board evidence policy.
- Fixed varied request set, comparison baseline, time/request/cost caps and acceptance criteria.

Suggested evaluation (proposal only): compare index-only and pipeline-assisted sourcing on matched natural-language requests and budgets; measure qualified yield, geography errors, availability evidence, unsupported claims, failures and agent portability. No implementation or evaluation has started.
