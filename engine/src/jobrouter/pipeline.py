"""One search mission, with explicit blocked/conditional stages and inspectable results."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from .discovery import discover
from .extraction import extract_facts
from .matching import screen, apply_review
from .models import Brief, now
from .routing import compile_brief, ModelError
from .verification import verify_application
from .identity import deduplicate


@dataclass
class SearchResult:
    started_at: str
    brief_digest: str
    qualified: list = field(default_factory=list)
    conditional: list = field(default_factory=list)
    excluded: list = field(default_factory=list)
    stages: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    status: str = "incomplete"


def run_search(prompt, profile, seeds, router, fetcher, store=None, candidate_limit=60,
               source_limit=100, workers=4, depth=2, compiled_brief=None, history=None):
    """Host model and transport dependencies are injected, never silently substituted."""
    if not 1 <= candidate_limit <= 1000:
        raise ValueError("Invalid candidate limit")
    brief = compiled_brief or compile_brief(prompt, profile, router)[0]
    brief.validate()
    if brief.prompt != prompt or brief.profile != profile:
        raise ValueError("Supplied brief does not match mission inputs")
    result = SearchResult(now(), brief.digest)
    result.stages.append({"stage": "interpret", "status": "completed", "unresolved": brief.unresolved})
    collected = discover(seeds, fetcher, store, max_sources=source_limit, depth=depth, workers=workers)
    result.stages.append({"stage": "discover", "status": "completed_with_gaps" if collected.errors else "completed",
                          "jobs": len(collected.jobs), "stop_reason": collected.stop_reason})
    result.errors.extend(collected.errors)
    history = history or {}
    kept, duplicates, uncertain_reposts = deduplicate(collected.jobs.values(), history.get("identities", []),
                                                    history.get("urls", []), history.get("fingerprints", []))
    result.stages.append({"stage": "deduplicate", "status": "completed_with_gaps" if uncertain_reposts else "completed",
                          "excluded": duplicates, "possible_reposts": uncertain_reposts,
                          "history_scope": history.get("scope", "No prior application history supplied")})
    ordered = sorted(kept, key=lambda x: (-screen(x, brief).score, x.identity))
    candidates = ordered[:candidate_limit]
    result.coverage = {"collected": len(ordered), "review_candidates": len(candidates),
                       "not_reviewed_due_to_limit": max(0, len(ordered) - len(candidates)), "sources": collected.sources}

    def assess(job):
        # Even a rejected/failed extraction preserves the original job for inspection.
        job, extractor_model = extract_facts(job, router)
        decision = screen(job, brief)
        if decision.category == "excluded":
            return job, decision, None
        review_response = router.call("reviewer", {
            "operation": "judge_relevance", "job_id": job.identity, "brief_digest": brief.digest,
            "brief": brief.__dict__, "job": job.to_dict(),
            "required_output": {"job_id": job.identity, "brief_digest": brief.digest,
                                "source_digest": "A description evidence digest from the job",
                                "relevant": "boolean", "score": "number 0-100", "quotes": "exact description substrings", "reasons": "list of concise fit/gap reasons",
                                "requirements": "For each generic requirement id: {verdict: pass|fail|unknown, quote: exact description text, reason}. Absence of evidence means unknown."},
            "rules": ["Judge actual duties and applicant evidence, not title overlap alone.",
                      "Portfolio simulations are not employment experience.",
                      "Do not certify legal eligibility or unknown facts.",
                      "Reject unrelated jobs and excessive seniority; clearly explain stretches."]})
        review = dict(review_response["output"], model=review_response["actual_model"])
        decision = apply_review(decision, job, review, brief)
        if decision.category != "excluded":
            verification = verify_application(job, fetcher)
            decision = apply_review(screen(job, brief), job, review, brief)
        else:
            verification = None
        return job, decision, verification

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(assess, job): job for job in candidates}
        for future in as_completed(futures):
            job = futures[future]
            try:
                job, decision, verification = future.result()
                row = {"job": job.to_dict(), "decision": decision.to_dict(), "verification": verification}
                if verification and verification.get("status") == "unverified":
                    result.errors.append({"job_id": job.identity, "stage": "verify_application",
                                          "error": verification.get("reason", "Application path remains unverified")})
                getattr(result, decision.category).append(row)
                if store:
                    store.job(job)
            except Exception as exc:
                result.errors.append({"job_id": job.identity, "stage": "assess", "error": str(exc)})
                decision = screen(job, brief)
                getattr(result, decision.category).append({"job": job.to_dict(), "decision": decision.to_dict(), "error": str(exc)})
    for group in (result.qualified, result.conditional, result.excluded):
        group.sort(key=lambda x: (-x["decision"]["score"], x["job"]["provider"], x["job"]["external_id"]))
    result.coverage.update({"request_attempts": fetcher.used, "model_calls": len(router.receipts),
                            "requested_results": brief.count, "qualified_results": len(result.qualified),
                            "shortfall": max(0, brief.count - len(result.qualified))})
    result.stages.append({"stage": "assess_and_verify", "status": "completed_with_gaps" if result.errors else "completed"})
    result.status = "sufficient_verified_results" if len(result.qualified) >= brief.count else "shortfall"
    return result
