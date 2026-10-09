"""Bounded public HTTPS transport with pinned DNS, pacing and request receipts."""
from dataclasses import dataclass, asdict
import hashlib
import http.client
import ipaddress
import json
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


def _resolve_worker(pipe, hostname):
    try:
        pipe.send({"addresses": list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)))})
    except Exception as exc:
        pipe.send({"error": str(exc)})
    finally:
        pipe.close()


def resolve_public(hostname, timeout):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(False)
    process = context.Process(target=_resolve_worker, args=(child, hostname), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise FetchError("DNS deadline exceeded")
        result = parent.recv()
        if "error" in result:
            raise FetchError(result["error"])
        addresses = result["addresses"]
        if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
            raise FetchError("Non-public DNS answer")
        return addresses[0]
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        parent.close()


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
        if budget < 1 or timeout <= 0 or max_bytes < 1 or per_origin_delay < 0:
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
        opener = build_opener(NoRedirect())
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        try:
            result = opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            result = exc
        with result:
            body = result.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise FetchError("Response exceeds byte limit")
            return Response(url, result.code, dict((k.lower(), v) for k, v in result.headers.items()), body, now())

    def _wire(self, url):
        p = urlsplit(url)
        if p.hostname in self.trusted_proxy_hosts:
            return self._proxy_wire(url)
        deadline = time.monotonic() + self.timeout
        address = resolve_public(p.hostname, self.timeout)
        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise FetchError("Fetch deadline exceeded")
            return value
        conn = http.client.HTTPConnection(p.hostname, 443, timeout=self.timeout)
        # Connect to the already-validated address; retain hostname TLS verification.
        raw = socket.create_connection((address, 443), timeout=remaining())
        try:
            raw.settimeout(remaining())
            conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname)
            conn.sock.settimeout(remaining())
            conn.request("GET", urlunsplit(("", "", p.path or "/", p.query, "")),
                         headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
            conn.sock.settimeout(remaining())
            result = conn.getresponse()
            headers = {k.lower(): v for k, v in result.getheaders()}
            if int(headers.get("content-length", "0")) > self.max_bytes:
                raise FetchError("Response exceeds byte limit")
            content = bytearray()
            while len(content) <= self.max_bytes:
                if conn.sock:
                    conn.sock.settimeout(remaining())
                else:
                    remaining()
                chunk = result.read1(min(65536, self.max_bytes + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            if len(content) > self.max_bytes:
                raise FetchError("Response exceeds byte limit")
            return Response(url, result.status, headers, bytes(content), now())
        finally:
            conn.close()
            raw.close()

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
