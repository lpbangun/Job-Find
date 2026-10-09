"""Evidence-bound semantic extraction. Source documents never choose tools or commands."""
from dataclasses import fields
import math
import re
from .models import Evidence
from .routing import ModelError


ALLOWED = {"arrangement", "employment", "countries", "salary_min", "salary_max", "currency", "salary_period",
           "salary_type", "hours_min", "hours_max", "experience_min", "required_skills", "sector", "sponsorship"}
ENUMS = {"arrangement": {"remote", "hybrid", "onsite", "unknown"},
         "employment": {"full-time", "part-time", "contract", "internship", "temporary", "unknown"},
         "salary_type": {"base", "ote", "unknown"}, "salary_period": {"year", "hour", "month", "week", "unknown"},
         "sponsorship": {"yes", "no", "unknown"}}


def apply_facts(job, output):
    if output.get("job_id") != job.identity:
        raise ModelError("Facts are bound to another job")
    facts = output.get("facts")
    if not isinstance(facts, dict):
        raise ModelError("Missing structured facts")
    pending = []
    for field, item in facts.items():
        if field not in ALLOWED or not isinstance(item, dict):
            raise ModelError(f"Unsupported fact field: {field}")
        value = item.get("value")
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote or quote not in job.description:
            raise ModelError(f"Missing exact description evidence: {field}")
        if field in ENUMS and value not in ENUMS[field]:
            raise ModelError(f"Invalid enumeration: {field}")
        if field.endswith(("_min", "_max")):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ModelError(f"Invalid numeric fact: {field}")
            numbers = []
            for match in re.finditer(r"(?<![\w.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([kK])?(?!\w)", quote):
                number = float(match.group(1).replace(",", "")) * (1000 if match.group(2) else 1)
                numbers.append(number)
            if value not in numbers:
                raise ModelError(f"Numeric fact is not present in its quote: {field}")
        if field in ("countries", "required_skills") and (not isinstance(value, list) or any(not isinstance(x, str) for x in value)):
            raise ModelError(f"Invalid fact list: {field}")
        if field in ("currency", "sector") and (not isinstance(value, str) or not value.strip()):
            raise ModelError(f"Invalid string fact: {field}")
        pending.append((field, value, quote))
    values = {field: value for field, value, quote in pending}
    for lo, hi in (("salary_min", "salary_max"), ("hours_min", "hours_max")):
        low, high = values.get(lo, getattr(job, lo)), values.get(hi, getattr(job, hi))
        if low is not None and high is not None and low > high:
            raise ModelError(f"Contradictory range: {lo}/{hi}")
    # Apply only after validating the whole response: no partial mutations on a rejected extraction.
    for field, value, quote in pending:
        setattr(job, field, value)
        job.evidence.append(Evidence.from_text(job.url, job.description, quote, field, job.observed_at))
    return job


def extract_facts(job, router):
    result = router.call("extractor", {"operation": "extract_job_facts", "job_id": job.identity,
        "title": job.title, "location": job.location, "description": job.description,
        "allowed_fields": sorted(ALLOWED), "enums": {k: sorted(v) for k, v in ENUMS.items()},
        "output_shape": {"job_id": job.identity, "facts": {"field": {"value": "typed value", "quote": "exact description substring"}}},
        "rules": ["Omit unknown facts. A remote label alone is not worldwide or US eligibility.",
                  "Distinguish mandatory skills from preferred and from product descriptions.",
                  "Training benefits are not instructional-design job duties.",
                  "Never convert OTE to base, currency or hourly to annual without explicit source facts.",
                  "Hours must be committed minimum/maximum, not an assumed full-time schedule.",
                  "Do not infer sponsorship denial from silence or work authorization requirements."]})
    return apply_facts(job, result["output"]), result["actual_model"]
