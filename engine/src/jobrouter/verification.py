"""Check current application evidence. Never submit a form."""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit
from .adapters import plain
from .models import Evidence, now
from .transport import canonical_url


POOLS = re.compile(r"\b(talent pool|talent community|spontaneous application|general application|open application|wild card|expression of interest)\b|\bpool$", re.I)
CLOSED = re.compile(r"(this (?:job|position|role) (?:is|has been) (?:no longer|closed|filled)|no longer accepting applications|job is no longer available)", re.I)


def verify_application(job, fetcher):
    if POOLS.search(job.title):
        job.availability = "lead"
        return {"job_id": job.identity, "status": "lead", "reason": "Evergreen/speculative pool is not a verified vacancy"}
    if job.deadline:
        try:
            expiry = datetime.fromisoformat(job.deadline.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < datetime.now(timezone.utc):
                job.availability = "closed"
                return {"job_id": job.identity, "status": "closed", "reason": "Published deadline has passed"}
        except ValueError:
            job.availability = "unverified"
            return {"job_id": job.identity, "status": "unverified", "reason": "Unparseable deadline"}
    try:
        if job.provider == "greenhouse":
            endpoint = f"https://boards-api.greenhouse.io/v1/boards/{job.board}/jobs/{job.external_id}?questions=true"
            response = fetcher.get(endpoint)
            data = response.json()
            questions = data.get("questions")
            if str(data.get("id")) != job.external_id or data.get("title") != job.title or not isinstance(questions, list) or not questions:
                raise ValueError("Exact posting application schema not established")
            if not data.get("absolute_url") or canonical_url(data["absolute_url"]) != canonical_url(job.url):
                raise ValueError("Application schema URL differs from the candidate's canonical URL")
            fields = [f.get("name", "") for q in questions for f in q.get("fields", [])]
            if "email" not in fields or not any(x in fields for x in ("first_name", "last_name", "full_name")):
                raise ValueError("Application identity fields not established")
            job.apply_url = job.url
            job.evidence.append(Evidence.from_text(response.url, response.text, '"questions"', "application_schema", response.observed_at))
        else:
            if job.provider == "structured" and any(e.field == "description" and canonical_url(e.url) != canonical_url(job.url) for e in job.evidence):
                raise ValueError("Off-site structured lead requires canonical description refresh before verification")
            url = job.url.rstrip("/") + "/apply" if job.provider == "lever" else job.url
            response = fetcher.get(url)
            text = plain(response.text)
            if CLOSED.search(text):
                job.availability = "closed"
                return {"job_id": job.identity, "status": "closed", "reason": "Official closed notice"}
            # Require posting identity and a real input form, not generic Apply marketing text.
            if job.title.casefold() not in text.casefold() or not re.search(r"<form\b", response.text, re.I):
                raise ValueError("Job-specific application form not present in retrieved HTML")
            if not re.search(r'<input\b[^>]*(?:name=["\'][^"\']*email|type=["\']email)', response.text, re.I):
                raise ValueError("Application email input not established")
            job.apply_url = response.url
            marker = re.search(r"<form\b[^>]*>", response.text, re.I).group()
            job.evidence.append(Evidence.from_text(response.url, response.text, marker, "application_form", response.observed_at))
        job.availability = "open"
        job.observed_at = response.observed_at
        return {"job_id": job.identity, "status": "open", "checked_at": job.observed_at,
                "apply_url": job.apply_url, "method": "read_only_application_schema" if job.provider == "greenhouse" else "read_only_form"}
    except Exception as exc:
        job.availability = "unverified"
        return {"job_id": job.identity, "status": "unverified", "checked_at": now(), "reason": str(exc)}
