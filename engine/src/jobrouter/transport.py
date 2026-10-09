"""Bounded public HTTPS transport with pinned DNS, pacing and request receipts."""
from dataclasses import dataclass, asdict
import hashlib
import http.client
import ipaddress
import json
import math
from pathlib import Path
import tempfile
import socket
import ssl
import threading
import time
import multiprocessing
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin
from urllib.request import build_opener, HTTPRedirectHandler, Request, getproxies
from urllib.error import HTTPError
from .models import now
from .robots import RobotsPolicy


class FetchError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_public(hostname):
    # Called only inside the bounded request worker: DNS consumes its deadline.
    addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise FetchError("Non-public DNS answer")
    return addresses[0]


def _direct_request_worker(directory, url, user_agent, timeout, max_bytes):
    """DNS, TLS and all HTTP framing run inside one parent-bounded process."""
    directory = Path(directory)
    conn = raw = None
    try:
        p = urlsplit(url)
        address = resolve_public(p.hostname)
        conn = http.client.HTTPConnection(p.hostname, 443, timeout=timeout)
        raw = socket.create_connection((address, 443), timeout=timeout)
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname)
        conn.request("GET", urlunsplit(("", "", p.path or "/", p.query, "")),
                     headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        with conn.getresponse() as result:
            headers = {k.lower(): v for k, v in result.getheaders()}
            if int(headers.get("content-length", "0")) > max_bytes:
                raise FetchError("Response exceeds byte limit")
            body = result.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("Response exceeds byte limit")
            metadata = {"status": result.status, "headers": headers, "observed_at": now()}
            (directory / "body").write_bytes(body)
    except Exception as exc:
        metadata = {"error": str(exc)[:4096]}
    finally:
        if conn is not None:
            conn.close()
        if raw is not None:
            raw.close()
    (directory / "result.json").write_text(json.dumps(metadata), encoding="utf-8")


def _proxy_request_worker(directory, url, user_agent, timeout, max_bytes):
    """Spawn-safe worker: all potentially trickling network reads stay here."""
    directory = Path(directory)
    try:
        opener = build_opener(NoRedirect())
        request = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        try:
            result = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            result = exc
        with result:
            body = result.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("Response exceeds byte limit")
            metadata = {"status": result.code,
                        "headers": {k.lower(): v for k, v in result.headers.items()},
                        "observed_at": now()}
            (directory / "body").write_bytes(body)
    except Exception as exc:
        metadata = {"error": str(exc)[:4096]}
    (directory / "result.json").write_text(json.dumps(metadata), encoding="utf-8")


def _reap_request_worker(process):
    # Network workers create no descendants. Bound the graceful stop before kill.
    if process.is_alive():
        process.terminate()
        process.join(timeout=0.2)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)
    if process.is_alive():
        raise FetchError("Request worker could not be reaped")
    process.join(timeout=0)
    process.close()


def canonical_url(url):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError("Unsafe URL")
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only credential-free public HTTPS on port 443")
    host = p.hostname.encode("idna").decode().lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private hostname")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private address")
    except ValueError as exc:
        if str(exc) == "Private address":
            raise
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")]
    host = f"[{host}]" if ":" in host else host
    return urlunsplit(("https", host, p.path or "/", urlencode(sorted(query)), ""))


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes
    observed_at: str

    @property
    def text(self):
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


class PublicFetcher:
    def __init__(self, budget=200, per_origin_delay=0.5, timeout=20, max_bytes=3_000_000, wire=None, trusted_proxy_hosts=()):
        if (budget < 1 or isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0 or max_bytes < 1 or per_origin_delay < 0):
            raise ValueError("Invalid fetch limits")
        self.budget = budget
        self.delay = per_origin_delay
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.used = 0
        self.receipts = []
        self._lock = threading.Lock()
        self._origin_locks = {}
        self._last = {}
        self._delays = {}
        self._robots = {}
        self._blocked = set()
        self.wire = wire or self._wire
        self.user_agent = "JobRouter/0.1 public-job-research"
        # Explicit deployment policy for managed environments whose trusted egress proxy
        # resolves public hosts. Never infer this allowlist from a scraped page or prompt.
        self.trusted_proxy_hosts = frozenset(trusted_proxy_hosts)

    def _proxy_wire(self, url):
        if urlsplit(url).hostname not in self.trusted_proxy_hosts or not getproxies().get("https"):
            raise FetchError("Host is not approved for the managed egress proxy")
        return self._isolated_wire(url, _proxy_request_worker, "Managed proxy")

    def _isolated_wire(self, url, worker, label):
        deadline = time.monotonic() + self.timeout

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise FetchError(f"{label} fetch deadline exceeded")
            return value

        # A pipe poll only promises some bytes, not a complete message. Wait for
        # worker exit instead, then read bounded files in a private local directory.
        with tempfile.TemporaryDirectory(prefix="jobrouter-request-") as directory:
            context = multiprocessing.get_context("spawn")
            process = context.Process(target=worker,
                                      args=(directory, url, self.user_agent, self.timeout, self.max_bytes),
                                      daemon=True)
            try:
                remaining()
                process.start()
                process.join(timeout=remaining())
                if process.is_alive():
                    raise FetchError(f"{label} fetch deadline exceeded")
                remaining()
                if process.exitcode != 0:
                    raise FetchError(f"{label} worker failed")
                try:
                    with open(Path(directory) / "result.json", "rb") as source:
                        raw_metadata = source.read(8_000_001)
                    if len(raw_metadata) > 8_000_000:
                        raise FetchError(f"{label} metadata exceeds byte limit")
                    metadata = json.loads(raw_metadata)
                    remaining()
                    if "error" in metadata:
                        raise FetchError(metadata["error"])
                    with open(Path(directory) / "body", "rb") as source:
                        body = source.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        raise FetchError("Response exceeds byte limit")
                    response = Response(url, metadata["status"], metadata["headers"], body, metadata["observed_at"])
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise FetchError(f"Invalid {label.lower()} worker result") from exc
                remaining()
                return response
            finally:
                if process.pid is not None:
                    _reap_request_worker(process)
                else:
                    process.close()

    def _wire(self, url):
        p = urlsplit(url)
        if p.hostname in self.trusted_proxy_hosts:
            return self._proxy_wire(url)
        return self._isolated_wire(url, _direct_request_worker, "Direct")

    def _one(self, url):
        url = canonical_url(url)
        origin = urlsplit(url).netloc
        with self._lock:
            lock = self._origin_locks.setdefault(origin, threading.RLock())
        with lock:
            if origin in self._blocked:
                raise FetchError("Origin stopped after an access or rate-limit response")
            wait = max(self.delay, self._delays.get(origin, 0)) - (time.monotonic() - self._last.get(origin, 0))
            if wait > 0:
                time.sleep(wait)
            with self._lock:
                if self.used >= self.budget:
                    raise FetchError("Request budget exhausted")
                self.used += 1
                sequence = self.used
            start = now()
            receipt = {"sequence": sequence, "url": url, "started_at": start,
                       "error": "Request interrupted before completion"}
            try:
                response = self.wire(url)
                if response.status in (401, 403, 429):
                    self._blocked.add(origin)
                receipt = {"sequence": sequence, "url": url, "started_at": start,
                           "status": response.status, "bytes": len(response.body),
                           "sha256": hashlib.sha256(response.body).hexdigest()}
                return response
            except Exception as exc:
                receipt = {"sequence": sequence, "url": url, "started_at": start, "error": str(exc)}
                raise
            finally:
                self._last[origin] = time.monotonic()
                with self._lock:
                    self.receipts.append(receipt)

    def _allowed(self, url):
        p = urlsplit(url)
        origin = p.netloc
        with self._lock:
            lock = self._origin_locks.setdefault(origin, threading.RLock())
        with lock:
            if origin not in self._robots:
                r = self._one(f"https://{origin}/robots.txt")
                if r.status == 404:
                    rules = ""
                elif r.status == 200 and "<html" not in r.text[:500].lower():
                    rules = r.text
                else:
                    self._robots[origin] = None
                    raise FetchError(f"Robots permission unresolved: HTTP {r.status}")
                parser = RobotsPolicy(rules, self.user_agent)
                self._delays[origin] = parser.delay
                self._robots[origin] = parser
            parser = self._robots[origin]
            if parser is None or not parser.allows(url):
                raise FetchError("Robots disallows path or permission is unresolved")

    def get(self, url):
        seen = set()
        for _ in range(5):
            url = canonical_url(url)
            if url in seen:
                raise FetchError("Redirect cycle")
            seen.add(url)
            self._allowed(url)
            r = self._one(url)
            if r.status in (301, 302, 303, 307, 308):
                if not r.headers.get("location"):
                    raise FetchError("Redirect missing Location")
                url = urljoin(url, r.headers["location"])
                continue
            if r.status in (401, 403, 429):
                raise FetchError(f"Access stopped: HTTP {r.status}")
            if r.status != 200:
                raise FetchError(f"HTTP {r.status}")
            return r
        raise FetchError("Redirect limit exceeded")
