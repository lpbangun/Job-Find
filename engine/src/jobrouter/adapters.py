"""Public ATS collection; source-specific schemas remain distinct."""
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
import json
from urllib.parse import urlsplit
from .models import Job, Evidence
from .transport import canonical_url


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, text):
        self.parts.append(text)


def plain(text):
    parser = TextParser()
    parser.feed(unescape(str(text or "")))
    return " ".join(" ".join(parser.parts).split())


@dataclass(frozen=True)
class Board:
    provider: str
    slug: str
    source_url: str

    @property
    def identity(self):
        return f"{self.provider}:{self.slug.lower()}"

    @property
    def endpoint(self):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", self.slug):
            raise ValueError("Invalid board slug")
        return {
            "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{self.slug}/jobs?content=true",
            "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{self.slug}?includeCompensation=true",
            "lever": f"https://api.lever.co/v0/postings/{self.slug}?mode=json",
            "workable": f"https://apply.workable.com/api/v1/widget/accounts/{self.slug}/",
            "recruitee": f"https://{self.slug}.recruitee.com/api/offers/",
        }[self.provider]


def detect_board(url):
    p = urlsplit(canonical_url(url))
    segments = p.path.strip("/").split("/")
    hostmap = {"jobs.ashbyhq.com": "ashby", "job-boards.greenhouse.io": "greenhouse",
               "boards.greenhouse.io": "greenhouse", "jobs.lever.co": "lever", "apply.workable.com": "workable"}
    provider = hostmap.get(p.hostname)
    if provider and segments[0] and re.fullmatch(r"[A-Za-z0-9._-]{1,120}", segments[0]):
        return Board(provider, segments[0], url)
    if p.hostname.endswith(".recruitee.com") and p.hostname.count(".") == 2:
        slug = p.hostname.split(".")[0]
        if slug not in ("www", "api", "app"):
            return Board("recruitee", slug, url)
    return None


def normalize(board, response):
    payload = response.json()
    key = {"greenhouse": "jobs", "ashby": "jobs", "workable": "jobs", "recruitee": "offers"}.get(board.provider)
    rows = payload.get(key) if key and isinstance(payload, dict) else payload if board.provider == "lever" else None
    if not isinstance(rows, list):
        raise ValueError("Invalid or incomplete board payload")
    # Preserve the exact source spelling, including optional JSON escapes such as \u0026.
    string_tokens = {}
    for match in re.finditer(r'"(?:[^"\\]|\\.)*"', response.text):
        try:
            string_tokens.setdefault(json.loads(match.group()), match.group()[1:-1])
        except ValueError:
            continue
    jobs = []
    seen = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed posting")
        if row.get("isListed") is False or (board.provider == "recruitee" and row.get("status") not in (None, "published")):
            continue
        categories = row.get("categories") or {}
        location = row.get("location") or ""
        if isinstance(location, dict):
            location = location.get("name") or location.get("location_str") or ", ".join(str(location.get(k, "")) for k in ("city", "country")).strip(", ")
        if not location:
            location = ", ".join(str(row[k]) for k in ("city", "state", "country") if row.get(k))
        title = row.get("title") or row.get("text")
        external_id = row.get("id") or row.get("shortcode") or row.get("guid")
        url = row.get("absolute_url") or row.get("jobUrl") or row.get("hostedUrl") or row.get("url") or row.get("shortlink") or row.get("careers_url")
        if not title or not external_id or not url:
            raise ValueError("Missing posting identity/title/URL; do not claim complete inventory")
        url = canonical_url(url)
        desc = row.get("content") or row.get("descriptionPlain") or row.get("description") or ""
        if board.provider == "lever":
            desc = " ".join([desc, *[f"{x.get('text', '')} {x.get('content', '')}" for x in row.get("lists", [])], row.get("additional", "")])
            location = categories.get("location", location)
        description = plain(desc)
        workplace = str(row.get("workplaceType") or row.get("workplace") or "").lower()
        arrangement = {"onsite": "onsite", "on-site": "onsite", "hybrid": "hybrid", "remote": "remote"}.get(workplace, "unknown")
        if row.get("isRemote") is True or row.get("remote") is True or row.get("telecommuting") is True:
            arrangement = "remote"
        employment = str(row.get("employmentType") or row.get("employment_type") or row.get("employment_type_code") or categories.get("commitment") or "unknown").lower().replace("_", "-")
        employment = {"fulltime": "full-time", "parttime": "part-time", "full time": "full-time", "part time": "part-time"}.get(employment, employment)
        job = Job(board.provider, board.slug, str(external_id), title, board.slug, url, description,
                  location=str(location), arrangement=arrangement, employment=employment,
                  observed_at=response.observed_at, published_at=row.get("publishedAt") or row.get("published_on"))
        # A board entry is evidence of a listing, not proof the application path works.
        title_quote = string_tokens.get(title)
        if title_quote is None:
            raise ValueError("Cannot bind decoded title to source JSON")
        job.evidence.append(Evidence.from_text(response.url, response.text, title_quote, "title", response.observed_at))
        if description:
            job.evidence.append(Evidence.from_text(url, description, description[:250], "description", response.observed_at))
        prior = seen.get(job.identity)
        if prior and prior != job.to_dict():
            raise ValueError("Conflicting duplicate posting ID")
        if not prior:
            seen[job.identity] = job.to_dict()
            jobs.append(job)
    return jobs
