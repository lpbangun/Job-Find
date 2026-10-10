"""Conservative deterministic screening; semantic relevance needs independent review."""
import re
import math
import hashlib
from datetime import datetime, timezone, timedelta
from .models import Brief, Job, Check, Decision, Verdict
from .verification import POOLS


FAMILIES = {
    "learning": ["instructional", "learning design", "learning engineer", "curriculum", "training", "enablement", "education", "facilitator"],
    "people": ["people operations", "human resources", "hr coordinator", "employee experience", "people coordinator"],
    "recruiting": ["recruit", "talent acquisition", "sourcing", "talent coordinator"],
    "implementation": ["implementation", "onboarding", "customer education", "solutions consultant", "deployment"],
    "operations": ["business operations", "founder", "chief of staff", "strategy", "program coordinator", "operations associate"],
    "engineering": ["software engineer", "developer", "backend", "frontend", "full stack", "infrastructure engineer"],
    "design": ["product design", "ux", "user experience", "visual designer", "researcher"],
    "sales": ["sales", "account executive", "business development", "sdr"],
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()



# Planner outputs are natural language, not an enum. Normalize common family
# names before expanding retrieval aliases; this never establishes relevance.
FAMILY_NAMES = {
    "engineering": {"software engineering", "software development", "backend software engineering",
                    "backend engineering", "frontend engineering", "front end engineering",
                    "full stack engineering", "fullstack engineering", "backend development",
                    "frontend development", "full stack development"},
    "learning": {"instructional design", "learning design", "learning and development", "education and training"},
    "people": {"human resources", "people operations", "hr"},
    "recruiting": {"recruitment", "talent acquisition", "technical recruiting"},
    "implementation": {"customer implementation", "customer onboarding", "software implementation"},
    "operations": {"business operations", "business strategy", "strategy and operations"},
    "design": {"product design", "ux design", "user experience design", "visual design"},
    "sales": {"business development", "sales development", "account sales"},
}


def retrieval_norm(value):
    value = norm(value)
    for source, target in (("front end", "frontend"), ("back end", "backend"), ("fullstack", "full stack")):
        value = re.sub(r"\b" + source + r"\b", target, value)
    return value


def title_match(term, title):
    # Short aliases are tokens, not fragments (ux must not match luxury).
    if len(term) <= 3:
        return re.search(r"\b" + re.escape(term) + r"\b", title) is not None
    return term in title


def retrieval_terms(families):
    terms = []
    for family in families:
        name = retrieval_norm(family)
        canonical = next((key for key, aliases in FAMILY_NAMES.items()
                          if name == key or name in aliases), None)
        # Exact aliases are also valid family labels. Unknown domains remain
        # literal, rather than being coerced into an unrelated known family.
        if canonical is None:
            canonical = next((key for key, aliases in FAMILIES.items()
                              if name in {norm(alias) for alias in aliases}), None)
        terms.extend(FAMILIES[canonical] if canonical else [name])
    return list(dict.fromkeys(terms))


def screen(job: Job, brief: Brief) -> Decision:
    brief.validate()
    checks = []
    def add(key, condition, reason):
        checks.append(Check(key, Verdict.UNKNOWN if condition is None else Verdict.PASS if condition else Verdict.FAIL, reason))

    current_application = False
    for evidence in job.evidence:
        if evidence.field not in ("application_schema", "application_form", "rendered_application_form"):
            continue
        try:
            current = datetime.now(timezone.utc)
            if evidence.expires_at is not None and current >= datetime.fromisoformat(evidence.expires_at.replace("Z", "+00:00")):
                continue
            # Rendered observations need the provider's short explicit expiry.
            if evidence.field == "rendered_application_form" and evidence.expires_at is None:
                continue
            age = current - datetime.fromisoformat(evidence.observed_at.replace("Z", "+00:00"))
            if timedelta(0) <= age <= timedelta(hours=24):
                current_application = True
        except (ValueError, TypeError):
            pass
    add("availability", True if job.availability == "open" and current_application else False if job.availability == "closed" else None,
        f"Official availability: {job.availability}")
    if POOLS.search(job.title):
        add("vacancy", False, "A talent pool or speculative application is not an active vacancy")
    if brief.arrangements:
        add("arrangement", None if job.arrangement == "unknown" else job.arrangement in brief.arrangements, job.arrangement)
    if brief.employment_types:
        add("employment", None if job.employment == "unknown" else job.employment in brief.employment_types, job.employment)
    if brief.country:
        add("country", brief.country.upper() in job.countries if job.countries else None,
            f"Explicit eligible countries: {job.countries}; remote does not mean worldwide")
    if brief.locations and job.arrangement != "remote":
        add("location", any(norm(x) in norm(job.location) for x in brief.locations) if job.location else None, job.location or "Location absent")
    if brief.minimum_base is not None:
        if job.salary_type != "base" or job.salary_period != "year" or job.currency != brief.currency or job.salary_max is None:
            add("salary", None, "Comparable annual base salary not established")
        elif job.salary_max < brief.minimum_base:
            add("salary", False, "Entire base range below floor")
        elif job.salary_min is None or job.salary_min < brief.minimum_base:
            add("salary", None, "Range overlaps floor; acceptable offer is not assured")
        else:
            add("salary", True, "Published base range meets floor")
    if brief.minimum_hours is not None:
        add("hours", None if job.hours_min is None else job.hours_min >= brief.minimum_hours,
            "Minimum guaranteed hours must meet the requirement")
    if brief.maximum_experience is not None:
        add("experience", None if job.experience_min is None else job.experience_min <= brief.maximum_experience,
            f"Required minimum experience: {job.experience_min}")
    if brief.excluded_sectors:
        add("sector", None if job.sector == "unknown" else norm(job.sector) not in [norm(x) for x in brief.excluded_sectors], job.sector)
    if brief.excluded_required_skills:
        # An empty list cannot prove that a skill is not mandatory; require a bound extraction receipt.
        documented = any(e.field == "required_skills" for e in job.evidence)
        banned = set(map(norm, brief.excluded_required_skills)) & set(map(norm, job.required_skills))
        add("required_skills", False if banned else True if documented else None,
            f"Excluded requirements present: {sorted(banned)}" if banned else "Requirements extraction required")
    if brief.needs_sponsorship:
        add("sponsorship", True if job.sponsorship == "yes" else False if job.sponsorship == "no" else None, job.sponsorship)
    for unresolved in brief.unresolved:
        add("unresolved_prompt", None, unresolved)
    for requirement in brief.requirements:
        add("requirement:" + requirement["id"], None, requirement["description"])

    title = retrieval_norm(job.title)
    terms = retrieval_terms(brief.role_families)
    hits = [term for term in terms if title_match(retrieval_norm(term), title)]
    # Candidate retrieval score is never sufficient to assert semantic fit.
    score = min(70.0, len(hits) * 20.0) if terms else 20.0
    engineering_families = [retrieval_norm(family) for family in brief.role_families
                            if retrieval_terms([family]) == FAMILIES["engineering"]]
    specialties = [specialty for specialty in ("backend", "frontend", "full stack")
                   if any(re.search(r"\b" + specialty + r"\b", family)
                          for family in engineering_families)]
    if specialties:
        # Keep broad discovery, but preserve an explicitly named specialty's
        # priority before the candidate budget truncates the list.
        specialty_hit = any(re.search(r"\b" + specialty + r"\b", title) for specialty in specialties)
        engineering_score = min(70, sum(title_match(retrieval_norm(term), title)
                                       for term in FAMILIES["engineering"]) * 20)
        engineering_score = 40 + min(30, engineering_score) if specialty_hit else min(30, engineering_score)
        other_families = [family for family in brief.role_families
                          if retrieval_terms([family]) != FAMILIES["engineering"]]
        other_score = min(70, sum(title_match(retrieval_norm(term), title)
                                 for term in retrieval_terms(other_families)) * 20)
        score = max(engineering_score, other_score)
    reasons = [f"Title retrieval match: {x}" for x in hits]
    if not hits and terms:
        reasons.append("No title-alias match; retain for semantic review rather than automatically exclude")
    category = "excluded" if any(c.verdict == Verdict.FAIL for c in checks) else "conditional"
    return Decision(job.identity, category, score, checks, reasons)


def apply_review(decision: Decision, job: Job, review: dict, brief: Brief) -> Decision:
    """Host model judgments are bound to the job, brief and source; hard failures cannot be overridden."""
    if review.get("job_id") != job.identity or review.get("brief_digest") != brief.digest:
        raise ValueError("Review is bound to another job or brief")
    description_digest = hashlib.sha256(job.description.encode()).hexdigest()
    if (review.get("source_digest") != description_digest or
            not any(e.field == "description" and e.digest == description_digest for e in job.evidence)):
        raise ValueError("Review must reference the current description snapshot")
    if not review.get("model") or not isinstance(review.get("relevant"), bool):
        raise ValueError("Actual model identity and relevance judgment required")
    quotes = review.get("quotes", [])
    if not quotes or any(not isinstance(q, str) or not q or q not in job.description for q in quotes):
        raise ValueError("Relevance must cite exact description evidence")
    score = review.get("score", decision.score)
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("Review score must be finite")
    reasons = review.get("reasons", [])
    if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons):
        raise ValueError("Review reasons must be a list of strings")
    requirement_reviews = review.get("requirements", {})
    if not isinstance(requirement_reviews, dict):
        raise ValueError("Requirement review must be an object")
    known_requirements = {r["id"] for r in brief.requirements}
    if set(requirement_reviews) - known_requirements:
        raise ValueError("Review contains an unknown requirement")
    updates = {}
    for key, item in requirement_reviews.items():
        if not isinstance(item, dict) or item.get("verdict") not in ("pass", "fail", "unknown"):
            raise ValueError("Invalid requirement verdict")
        proof = item.get("quote")
        if item["verdict"] != "unknown" and (not isinstance(proof, str) or not proof or proof not in job.description):
            raise ValueError("Requirement pass/fail needs exact source evidence")
        updates["requirement:" + key] = (Verdict(item["verdict"]), item.get("reason", "Evidence-bound semantic requirement review"))
    for check in decision.checks:
        if check.criterion in updates and check.verdict == Verdict.UNKNOWN:
            check.verdict, check.reason = updates[check.criterion]
    decision.model = review["model"]
    decision.reviewed = True
    decision.reasons.extend(reasons)
    if not review["relevant"] or any(x.verdict == Verdict.FAIL for x in decision.checks):
        decision.category = "excluded"
    elif any(x.verdict == Verdict.UNKNOWN for x in decision.checks):
        decision.category = "conditional"
    else:
        decision.category = "qualified"
    decision.score = max(0, min(100, float(score)))
    return decision
