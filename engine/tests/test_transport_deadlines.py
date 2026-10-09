"""Offline spawn-process fixtures; these tests never open a network connection."""
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from jobrouter import transport
from jobrouter.transport import FetchError, PublicFetcher


_REAL_WORKER = transport._proxy_request_worker
URL = "https://jobs.example/ok"


class FixtureResponse(io.BytesIO):
    code = 200
    headers = {"Content-Type": "text/plain"}


class TrickleResponse(FixtureResponse):
    def read(self, size=-1):
        # Individual reads keep making progress, but completion is far too late.
        for _ in range(size):
            time.sleep(0.05)
        return b"x" * size


class FixtureOpener:
    def open(self, request, timeout):
        assert request.get_header("Accept-encoding") == "identity"
        assert request.get_header("User-agent") == "JobRouter/0.1 public-job-research"
        mode = request.full_url.rsplit("/", 1)[-1]
        if mode in ("open-slow", "headers-slow"):
            time.sleep(20)
        if mode == "error":
            raise OSError("fixture network failure")
        if mode in ("403", "429", "302", "404"):
            raise HTTPError(request.full_url, int(mode), "fixture", {"Location": "/next"}, io.BytesIO(b"error body"))
        if mode == "body-slow":
            return TrickleResponse()
        return FixtureResponse(b"hello")


def fixture_worker(directory, url, user_agent, timeout, max_bytes):
    # Imported top-level function works under spawn, without inheriting mocks.
    mode = url.rsplit("/", 1)[-1]
    if mode == "kill":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (Path(directory) / "ready").write_text("ready")
        time.sleep(20)
    if mode == "handoff-slow":
        (Path(directory) / "result.json").write_text('{"status":')
        time.sleep(20)
    if mode == "crash":
        os._exit(7)
    if mode == "oversize-result":
        (Path(directory) / "result.json").write_text(json.dumps({"status": 200, "headers": {}, "observed_at": "fixture"}))
        (Path(directory) / "body").write_bytes(b"x" * (max_bytes + 1))
        return
    with patch.object(transport, "build_opener", return_value=FixtureOpener()) as opener:
        _REAL_WORKER(directory, url, user_agent, timeout, max_bytes)
        assert isinstance(opener.call_args.args[0], transport.NoRedirect)


class ProxyDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(transport, "_proxy_request_worker", fixture_worker),
                        patch.object(transport, "getproxies", return_value={"https": "http://fixture.invalid"})]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def fetcher(self, **kwargs):
        return PublicFetcher(per_origin_delay=0, trusted_proxy_hosts={"jobs.example"}, **kwargs)

    def test_spawn_success_and_receipt(self):
        fetcher = self.fetcher(timeout=3)
        response = fetcher._one(URL)
        self.assertEqual((response.status, response.body), (200, b"hello"))
        self.assertEqual(response.headers, {"content-type": "text/plain"})
        self.assertTrue(response.observed_at)
        self.assertEqual(fetcher.used, 1)
        self.assertEqual(fetcher.receipts[0]["sha256"], hashlib.sha256(b"hello").hexdigest())

    def test_http_errors_are_responses_and_no_redirect(self):
        for status in (302, 404):
            with self.subTest(status=status):
                response = self.fetcher(timeout=3)._proxy_wire(f"https://jobs.example/{status}")
                self.assertEqual(response.status, status)
                self.assertEqual(response.body, b"error body")
                self.assertEqual(response.headers["location"], "/next")

    def test_access_stops_and_no_retry(self):
        for status in (403, 429):
            with self.subTest(status=status):
                fetcher = self.fetcher(timeout=3)
                self.assertEqual(fetcher._one(f"https://jobs.example/{status}").status, status)
                with self.assertRaisesRegex(FetchError, "Origin stopped"):
                    fetcher._one(URL)
                self.assertEqual(fetcher.used, 1)
                self.assertEqual(len(fetcher.receipts), 1)

    def test_body_limit_in_worker_and_parent(self):
        self.assertEqual(self.fetcher(timeout=3, max_bytes=5)._proxy_wire(URL).body, b"hello")
        for mode in ("ok", "oversize-result"):
            with self.subTest(mode=mode), self.assertRaisesRegex(FetchError, "byte limit"):
                self.fetcher(timeout=3, max_bytes=4)._proxy_wire(f"https://jobs.example/{mode}")

    def test_error_and_crash_receipts(self):
        for mode, message in (("error", "fixture network failure"), ("crash", "worker failed")):
            fetcher = self.fetcher(timeout=3)
            with self.subTest(mode=mode), self.assertRaisesRegex(FetchError, message):
                fetcher._one(f"https://jobs.example/{mode}")
            self.assertEqual(fetcher.used, 1)
            self.assertEqual(len(fetcher.receipts), 1)
            self.assertIn(message, fetcher.receipts[0]["error"])

    def test_deadline_covers_open_body_and_partial_result_cleanup(self):
        for mode in ("open-slow", "headers-slow", "body-slow", "handoff-slow", "kill"):
            directories, pids, ready = [], [], []
            real_temporary = tempfile.TemporaryDirectory
            real_reap = transport._reap_proxy_worker

            def temporary(*args, **kwargs):
                result = real_temporary(*args, **kwargs)
                directories.append(result.name)
                return result

            def reap(process):
                pids.append(process.pid)
                ready.append((Path(directories[0]) / "ready").exists())
                real_reap(process)

            fetcher = self.fetcher(timeout=0.5, max_bytes=100)
            started = time.monotonic()
            with self.subTest(mode=mode), patch.object(transport.tempfile, "TemporaryDirectory", temporary), patch.object(transport, "_reap_proxy_worker", reap):
                with self.assertRaisesRegex(FetchError, "deadline exceeded"):
                    fetcher._one(f"https://jobs.example/{mode}")
                self.assertLess(time.monotonic() - started, 3)
                self.assertEqual(len(fetcher.receipts), 1)
                self.assertIn("deadline exceeded", fetcher.receipts[0]["error"])
                self.assertEqual(fetcher.used, 1)
                self.assertEqual(len(pids), 1)
                self.assertFalse(any(child.pid in pids for child in multiprocessing.active_children()))
                if os.name == "posix":
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pids[0], 0)
                self.assertFalse(any(Path(directory).exists() for directory in directories))
                if mode == "kill":
                    self.assertTrue(ready[0], "fixture must install SIGTERM handler before timeout")

    def test_startup_consumes_same_deadline(self):
        context = multiprocessing.get_context("spawn")
        real_process = context.Process

        class SlowStart:
            def __init__(self, *args, **kwargs):
                self.process = real_process(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self.process, name)

            def start(self):
                self.process.start()
                time.sleep(0.3)

        with patch.object(context, "Process", SlowStart), patch.object(transport.multiprocessing, "get_context", return_value=context):
            with self.assertRaisesRegex(FetchError, "deadline exceeded"):
                self.fetcher(timeout=0.2)._proxy_wire(URL)

    def test_parent_result_decode_consumes_same_deadline(self):
        real_loads = json.loads

        def slow_loads(value):
            time.sleep(0.6)
            return real_loads(value)

        with patch.object(transport.json, "loads", slow_loads):
            with self.assertRaisesRegex(FetchError, "deadline exceeded"):
                self.fetcher(timeout=0.5)._proxy_wire(URL)

    def test_exact_allowlist_and_proxy_required_before_spawn(self):
        with patch.object(transport.multiprocessing, "get_context") as context:
            for url in ("https://other.example/", "https://sub.jobs.example/", "https://jobs.example.evil/"):
                with self.assertRaisesRegex(FetchError, "not approved"):
                    self.fetcher()._proxy_wire(url)
            with patch.object(transport, "getproxies", return_value={}):
                with self.assertRaisesRegex(FetchError, "not approved"):
                    self.fetcher()._proxy_wire(URL)
            context.assert_not_called()

    def test_cancellation_preserves_exception_and_receipt(self):
        for interruption in (KeyboardInterrupt, SystemExit):
            def interrupted_wire(url):
                raise interruption()
            fetcher = PublicFetcher(wire=interrupted_wire, per_origin_delay=0)
            with self.assertRaises(interruption):
                fetcher._one(URL)
            self.assertEqual(fetcher.used, 1)
            self.assertEqual(len(fetcher.receipts), 1)
            self.assertIn("interrupted", fetcher.receipts[0]["error"])

    def test_timeout_must_be_finite_positive_number(self):
        for timeout in (0, -1, float("nan"), float("inf"), -float("inf"), True, None, "2"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.fetcher(timeout=timeout)


if __name__ == "__main__":
    unittest.main()
