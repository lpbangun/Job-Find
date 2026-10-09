"""Concurrent, bounded link frontier. Any permitted public source can supply leads."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from collections import deque
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlsplit
from .adapters import detect_board, normalize, plain
from .models import Job, Evidence
from .transport import canonical_url


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self._json = False
        self._data = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._json = True
            self._data = []
    def handle_data(self, data):
        if self._json:
            self._data.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self._json:
            self.scripts.append("".join(self._data))
            self._json = False


def structured_jobs(response):
    parser = Links()
    parser.feed(response.text)
    jobs = []
    for script in parser.scripts:
        try:
            data = json.loads(script)
        except ValueError:
            continue
        todo = data if isinstance(data, list) else [data]
        while todo:
            row = todo.pop()
            if not isinstance(row, dict):
                continue
            todo.extend(row.get("@graph", []))
            if row.get("@type") != "JobPosting" or not row.get("title") or not row.get("description"):
                continue
            url = canonical_url(urljoin(response.url, row.get("url") or response.url))
            identifier = row.get("identifier", {})
            ident = identifier.get("value") if isinstance(identifier, dict) else identifier
            org = row.get("hiringOrganization") or {}
            description = plain(row["description"])
            job = Job("structured", urlsplit(url).hostname, str(ident or url), row["title"], org.get("name", "Unknown"), url, description,
                      published_at=row.get("datePosted"), deadline=row.get("validThrough"), observed_at=response.observed_at)
            job.evidence.append(Evidence.from_text(response.url, description, description[:250], "description", response.observed_at))
            jobs.append(job)
    return jobs, parser.links


@dataclass
class DiscoveryResult:
    jobs: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    requests: int = 0
    stop_reason: str = "frontier_exhausted"


def discover(seeds, fetcher, store=None, max_sources=100, depth=2, workers=6):
    if workers < 1 or workers > 32 or max_sources < 1 or depth < 0:
        raise ValueError("Invalid frontier limits")
    queue = deque((canonical_url(x), None, 0) for x in seeds)
    seen_urls = set()
    seen_boards = set()
    result = DiscoveryResult()

    def visit(url):
        board = detect_board(url)
        response = fetcher.get(board.endpoint if board else url)
        if board:
            return normalize(board, response), [], "ats"
        jobs, links = structured_jobs(response)
        return jobs, links, "web"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and len(seen_urls) < max_sources:
            batch = []
            while queue and len(batch) < workers and len(seen_urls) < max_sources:
                url, parent, level = queue.popleft()
                board = detect_board(url)
                if url in seen_urls or (board and board.identity in seen_boards):
                    continue
                seen_urls.add(url)
                if board:
                    seen_boards.add(board.identity)
                batch.append((url, parent, level))
            pending = {pool.submit(visit, u): (u, p, d) for u, p, d in batch}
            for future in as_completed(pending):
                url, parent, level = pending[future]
                try:
                    jobs, links, kind = future.result()
                    result.sources.append({"url": url, "parent": parent, "kind": kind, "jobs": len(jobs)})
                    if store:
                        store.source(url, parent, kind, "collected")
                    for job in jobs:
                        result.jobs[job.identity] = job
                        if store:
                            store.job(job)
                    if level < depth:
                        candidates = []
                        for link in links:
                            try:
                                candidate = canonical_url(urljoin(url, link))
                                is_board = detect_board(candidate)
                                # Broad source traversal is explicit and bounded, not a fixed employer list.
                                if is_board or re.search(r"career|jobs|hiring|portfolio|companies|members|talent", candidate, re.I):
                                    candidates.append((candidate, url, level + 1))
                            except (ValueError, KeyError):
                                continue
                        queue.extend(sorted(set(candidates)))
                except Exception as exc:
                    result.errors.append({"url": url, "error": str(exc)})
                    if store:
                        store.source(url, parent, "unknown", "failed", str(exc))
            if fetcher.used >= fetcher.budget:
                result.stop_reason = "request_budget"
                break
    if queue and result.stop_reason == "frontier_exhausted":
        result.stop_reason = "source_limit"
    result.requests = fetcher.used
    if store:
        store.receipts(fetcher.receipts)
    return result
