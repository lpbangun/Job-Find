"""Canonical identities and conservative equivalent-reposting flags."""
import hashlib
import re
from urllib.parse import urlsplit, parse_qs


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def canonical_job_id(url):
    p = urlsplit(url)
    parts = p.path.strip("/").split("/")
    if p.hostname in ("job-boards.greenhouse.io", "boards.greenhouse.io") and len(parts) >= 3 and parts[1] == "jobs":
        return f"greenhouse:{parts[0].lower()}:{parts[2]}"
    if p.hostname in ("jobs.lever.co", "jobs.eu.lever.co") and len(parts) >= 2:
        return f"lever:{parts[0].lower()}:{parts[1]}"
    if p.hostname == "jobs.ashbyhq.com" and len(parts) >= 2:
        return f"ashby:{parts[0].lower()}:{parts[1]}"
    if p.hostname == "apply.workable.com":
        match = re.search(r"/(?:j)/([a-z0-9]+)", p.path, re.I)
        if match:
            return f"workable:any:{match.group(1).upper()}"
    return None


def repost_fingerprint(job):
    company = normalized(job.company)
    title = normalized(job.title)
    title = re.sub(r"\b(m f d|f m d|all genders|remote)\b", "", title)
    title = " ".join(title.split())
    location = normalized(job.location)
    description = normalized(job.description)
    return hashlib.sha256("|".join((company, title, location, description)).encode()).hexdigest()


def deduplicate(jobs, prior_identities=(), prior_urls=(), prior_fingerprints=()):
    """Exact historical identities exclude; equivalent distinct requisitions are review flags."""
    prior = set(prior_identities) | {x for url in prior_urls if (x := canonical_job_id(url))}
    historical_fingerprints = set(prior_fingerprints)
    seen_ids, seen_urls, seen_fingerprints = set(), set(), {}
    kept, rejected, uncertain = [], [], []
    for job in jobs:
        identity = canonical_job_id(job.url) or job.identity
        fingerprint = repost_fingerprint(job)
        if job.identity in prior or identity in prior:
            rejected.append({"job_id": job.identity, "reason": "known historical identity"})
            continue
        if job.identity in seen_ids or identity in seen_urls:
            rejected.append({"job_id": job.identity, "reason": "duplicate canonical identity"})
            continue
        if fingerprint in historical_fingerprints or fingerprint in seen_fingerprints:
            uncertain.append({"job_id": job.identity, "reason": "equivalent-description repost requires review",
                              "other": seen_fingerprints.get(fingerprint, "history")})
            continue
        seen_ids.add(job.identity)
        seen_urls.add(identity)
        seen_fingerprints[fingerprint] = job.identity
        kept.append(job)
    return kept, rejected, uncertain
