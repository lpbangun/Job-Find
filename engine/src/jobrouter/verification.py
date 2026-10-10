"""Check current application evidence. Never submit a form."""
from datetime import datetime, timezone
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit
from .models import Evidence, now
from .transport import canonical_url


POOLS = re.compile(r"\b(talent pool|talent community|spontaneous application|general application|open application|wild card|expression of interest)\b|\bpool$", re.I)
CLOSED = re.compile(r"(this (?:job|position|role) (?:is|has been) (?:no longer|closed|filled)|no longer accepting applications|job is no longer available)", re.I)


APPLICATION_INTENT = re.compile(r"\b(apply|application)\b", re.I)
OTHER_INTENT = re.compile(r"\b(newsletter|subscribe|subscription|contact|sign[ -]?up|register|registration)\b", re.I)
NAME_FIELDS = {"name", "fullname", "firstname", "lastname", "applicantname", "candidatename"}
JOB_ID_FIELDS = {"jobid", "positionid", "jobpostingid", "postingid", "requisitionid"}
HIDDEN_STYLE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))"
    r"\s*(?:!\s*important\s*)?(?:;|$)", re.I,
)


def _field_name(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


class _ApplicationForms(HTMLParser):
    """Conservative static evidence only; never execute scripts or submit controls."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.current = None
        self.button = None
        self.fieldsets = []
        self.elements = []
        self.ignored = []
        self.text = []
        self.has_base = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.append(tag)
            return
        if tag in {"script", "style", "template", "noscript"}:
            self.ignored.append(tag)
            return
        # Only obvious inline hiding is checked; this is not computed CSS proof.
        style = re.sub(r"/\*.*?\*/", "", attrs.get("style") or "", flags=re.S)
        unavailable = ("hidden" in attrs or "inert" in attrs or
                       (attrs.get("aria-disabled") or "").casefold() == "true" or
                       bool(HIDDEN_STYLE.search(style)))
        ancestor_unavailable = any(blocked for _, blocked in self.elements)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.elements.append((tag, unavailable))
        if tag == "base" and "href" in attrs:
            self.has_base = True
        if tag == "fieldset":
            self.fieldsets.append("disabled" in attrs)
        if tag == "form":
            if self.current is not None:
                self.current["invalid"] = True
                return
            self.current = {"attrs": attrs, "marker": self.get_starttag_text(),
                            "inputs": [], "hidden_ids": [], "submits": [], "text": [],
                            "invalid": "disabled" in attrs or any(self.fieldsets) or unavailable or ancestor_unavailable}
            self.forms.append(self.current)
        if self.current is None or tag not in {"input", "button"}:
            return
        # Explicit ownership must agree with lexical scope. External controls are
        # deliberately unsupported rather than borrowed from an unrelated form.
        if "form" in attrs and (not attrs["form"] or attrs["form"] != self.current["attrs"].get("id")):
            return
        kind = (attrs.get("type") or ("submit" if tag == "button" else "text")).lower()
        if tag == "input" and kind == "hidden" and _field_name(attrs.get("name") or "") in JOB_ID_FIELDS:
            self.current["hidden_ids"].append(attrs.get("value") or "")
        if "disabled" in attrs or any(self.fieldsets) or unavailable or ancestor_unavailable:
            return
        if tag == "input":
            self.current["inputs"].append((kind, attrs))
        if kind == "submit":
            control = {"attrs": attrs, "text": []}
            self.current["submits"].append(control)
            if tag == "button":
                self.button = control

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        for index in range(len(self.elements) - 1, -1, -1):
            if self.elements[index][0] == tag:
                del self.elements[index:]
                break
        if tag == "fieldset" and self.fieldsets:
            self.fieldsets.pop()
        elif tag == "button":
            self.button = None
        elif tag == "form":
            self.current = None
            self.button = None

    def handle_data(self, data):
        if self.ignored or any(blocked for _, blocked in self.elements):
            return
        self.text.append(data)
        if self.current is not None:
            self.current["text"].append(data)
        if self.button is not None:
            self.button["text"].append(data)


def _verified_form(parser, job, page_url):
    if parser.has_base:
        return None  # A base element changes relative URL semantics.
    origin = urlsplit(canonical_url(job.url)).netloc
    if urlsplit(canonical_url(page_url)).netloc != origin:
        return None
    for form in parser.forms:
        attrs = form["attrs"]
        context = " ".join(attrs.get(k) or "" for k in ("id", "name", "class", "aria-label", "action"))
        if (form["invalid"] or OTHER_INTENT.search(context) or
                any(value and value != job.external_id for value in form["hidden_ids"])):
            continue
        inputs = form["inputs"]
        name = any(kind == "text" and _field_name(a.get("name") or "") in NAME_FIELDS
                   for kind, a in inputs)
        email = any((kind == "email" and bool(a.get("name"))) or
                    (kind == "text" and _field_name(a.get("name") or "") in
                     {"email", "emailaddress", "applicantemail", "candidateemail"})
                    for kind, a in inputs)
        if not name or not email:
            continue
        hidden_binding = any(kind == "hidden" and _field_name(a.get("name") or "") in JOB_ID_FIELDS
                             and a.get("value") == job.external_id for kind, a in inputs)
        for submit in form["submits"]:
            control = submit["attrs"]
            label = " ".join(submit["text"] + [control.get(k) or "" for k in ("value", "aria-label", "name")])
            if not APPLICATION_INTENT.search(label) or OTHER_INTENT.search(label):
                continue
            action = control.get("formaction", attrs.get("action"))
            try:
                if action and (any(ord(c) < 33 for c in action) or "\\" in action):
                    continue
                target = canonical_url(urljoin(page_url, action or page_url))
                if urlsplit(target).netloc != origin:
                    continue
                segments = [unquote(segment) for segment in urlsplit(target).path.split("/")]
                if any(segment in {".", ".."} or "/" in segment or "\\" in segment for segment in segments):
                    continue
            except ValueError:
                continue
            path_binding = bool(action and job.external_id and job.external_id in segments)
            if hidden_binding or path_binding:
                return form["marker"]
    return None


def verify_application(job, fetcher, browser_provider=None):
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
            parser = _ApplicationForms()
            parser.feed(response.text)
            parser.close()
            text = " ".join(parser.text)
            if CLOSED.search(text):
                job.availability = "closed"
                return {"job_id": job.identity, "status": "closed", "reason": "Official closed notice"}
            # Visible posting identity plus enabled, job-bound controls in one form.
            marker = _verified_form(parser, job, response.url)
            if not job.title or job.title.casefold() not in text.casefold() or marker is None:
                if browser_provider is not None:
                    from .browser_verification import BrowserApplicationVerifier
                    if type(browser_provider) is not BrowserApplicationVerifier:
                        raise ValueError("Rendered verification requires the deployment-owned browser provider")
                    return browser_provider.verify(job)
                raise ValueError("Job-specific enabled application form and exact job binding not established")
            job.apply_url = response.url
            job.evidence.append(Evidence.from_text(response.url, response.text, marker, "application_form", response.observed_at))
        job.availability = "open"
        job.observed_at = response.observed_at
        return {"job_id": job.identity, "status": "open", "checked_at": job.observed_at,
                "apply_url": job.apply_url, "submission_tested": False, "method": "read_only_application_schema" if job.provider == "greenhouse" else "read_only_form"}
    except Exception as exc:
        job.availability = "unverified"
        return {"job_id": job.identity, "status": "unverified", "checked_at": now(), "reason": str(exc)}
