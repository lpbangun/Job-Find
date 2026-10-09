import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from jobrouter.adapters import Board, detect_board, normalize
from jobrouter.discovery import discover
from jobrouter.evaluation import evaluate
from jobrouter.matching import screen, apply_review
from jobrouter.models import Job, Brief, Evidence, Verdict
from jobrouter.store import Store
from jobrouter.transport import PublicFetcher, Response, FetchError, canonical_url


def response(url, data, status=200, headers=None):
    body = data if isinstance(data, str) else json.dumps(data)
    return Response(url, status, headers or {}, body.encode(), "2026-10-09T06:00:00+00:00")


def job(**kwargs):
    base = dict(provider="greenhouse", board="example", external_id="1", title="Learning Designer",
                company="Example", url="https://example.com/jobs/1", description="Design learning experiences.")
    base.update(kwargs)
    result = Job(**base)
    result.evidence = [Evidence.from_text(result.url, result.description, "Design learning", "description")]
    return result


class MatchingTests(unittest.TestCase):
    def test_unknown_not_pass(self):
        result = screen(job(), Brief("Remote learning", arrangements=["remote"]))
        self.assertEqual(result.category, "conditional")
        self.assertTrue(any(x.verdict == Verdict.UNKNOWN for x in result.checks))

    def test_remote_not_worldwide(self):
        result = screen(job(arrangement="remote", availability="open"), Brief("Remote US", country="US"))
        self.assertEqual(result.checks[-1].verdict, Verdict.UNKNOWN)

    def test_floor_ote_and_overlap(self):
        brief = Brief("Learning", minimum_base=55000)
        for extra, expected in [({"salary_type": "ote", "salary_min": 90000}, Verdict.UNKNOWN),
                                ({"salary_type": "base", "salary_min": 50000}, Verdict.UNKNOWN),
                                ({"salary_type": "base", "salary_min": 55000}, Verdict.PASS)]:
            result = screen(job(salary_max=95000, currency="USD", salary_period="year", **extra), brief)
            self.assertEqual(result.checks[-1].verdict, expected)

    def test_reviewer_cannot_override_failure(self):
        candidate = job(availability="closed")
        brief = Brief("Learning")
        decision = screen(candidate, brief)
        review = dict(job_id=candidate.identity, brief_digest=brief.digest, source_digest=candidate.evidence[0].digest,
                      model="test-reviewer", relevant=True, quotes=["Design learning"], score=100)
        self.assertEqual(apply_review(decision, candidate, review, brief).category, "excluded")
        review["quotes"] = ["fabricated"]
        with self.assertRaises(ValueError):
            apply_review(decision, candidate, review, brief)

    def test_review_brief_binding(self):
        candidate = job(availability="open")
        brief = Brief("Learning")
        with self.assertRaises(ValueError):
            apply_review(screen(candidate, brief), candidate, {"job_id": candidate.identity, "brief_digest": "other"}, brief)

    def test_no_profile_inheritance(self):
        self.assertIsNone(Brief("Find developers in India").profile)
        self.assertIsNone(Brief("Find developers in India").country)

    def test_open_claim_without_application_receipt_is_unknown(self):
        decision = screen(job(availability="open"), Brief("Learning"))
        self.assertEqual(decision.checks[0].verdict, Verdict.UNKNOWN)

    def test_nonfinite_brief(self):
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                Brief("Learning", minimum_base=value).validate()

    def test_abstention_not_perfect(self):
        result = evaluate({"a": []}, {"a": ["1"]})
        self.assertIsNone(result["micro_precision"])
        self.assertFalse(result["release_pass"])

    def test_duplicate_slots_not_refilled(self):
        result = evaluate({"a": ["1", "1", "2"]}, {"a": ["1", "2"]}, required_count=2)
        self.assertEqual(result["cases"][0]["relevant"], 1)
        self.assertEqual(result["cases"][0]["duplicate_slots"], 1)
        self.assertEqual(result["cases"][0]["strict_precision_at_k"], .5)


class CollectionTests(unittest.TestCase):
    def test_canonical_security(self):
        for value in ["http://x.com", "https://localhost", "https://127.0.0.1", "https://x.com:444", "https://user:pass@x.com", "https://x.com/\n"]:
            with self.assertRaises(ValueError, msg=value):
                canonical_url(value)
        self.assertEqual(canonical_url("https://EXAMPLE.com/jobs?utm_source=x&a=2#hi"), "https://example.com/jobs?a=2")

    def test_detection(self):
        self.assertEqual(detect_board("https://jobs.ashbyhq.com/test/id").identity, "ashby:test")
        self.assertIsNone(detect_board("https://jobs.ashbyhq.com.attacker.com/test"))

    def test_atomic_request_budget(self):
        f = PublicFetcher(budget=5, per_origin_delay=0, wire=lambda u: response(u, ""))
        def request(i):
            try:
                f.get(f"https://host{i}.example.com/jobs")
            except FetchError:
                pass
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(request, range(20)))
        self.assertEqual(f.used, 5)
        self.assertEqual(len(f.receipts), 5)

    def test_robots_and_access_stops(self):
        f = PublicFetcher(wire=lambda u: response(u, "User-agent: *\nDisallow: /private"), per_origin_delay=0)
        with self.assertRaises(FetchError):
            f.get("https://example.com/private")
        self.assertEqual(f.used, 1)
        g = PublicFetcher(wire=lambda u: response(u, "", 404 if u.endswith("robots.txt") else 429), per_origin_delay=0)
        with self.assertRaises(FetchError):
            g.get("https://example.com/jobs")
        with self.assertRaises(FetchError):
            g.get("https://example.com/jobs")
        self.assertEqual(g.used, 2)

    def test_end_to_end_discovery_store_rank(self):
        def wire(url):
            if url.endswith("robots.txt"):
                return response(url, "")
            if "boards-api" in url:
                return response(url, {"jobs": [{"id": 1, "title": "Learning Designer", "absolute_url": "https://job-boards.greenhouse.io/test/jobs/1", "content": "Design learning experiences."}]})
            return response(url, '<a href="https://job-boards.greenhouse.io/test">Careers</a>')
        f = PublicFetcher(wire=wire, per_origin_delay=0)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "public.sqlite")
            result = discover(["https://example.com/careers"], f, store)
            self.assertEqual(len(result.jobs), 1)
            candidate = Job.from_dict(store.jobs()[0])
            self.assertEqual(screen(candidate, Brief("learning", role_families=["learning"])).category, "conditional")
            self.assertEqual(f.used, 4)

    def test_malformed_not_empty_success(self):
        with self.assertRaises(ValueError):
            normalize(Board("greenhouse", "test", "https://example.com"), response("https://example.com", {"error": "rate limit"}))

    def test_encoded_json_title_evidence(self):
        data = {"jobs": [{"id": 2, "title": 'Learning Designer – "Advanced"', "absolute_url": "https://example.com/job/2", "content": "Learning"}]}
        jobs = normalize(Board("greenhouse", "test", "https://example.com"), response("https://example.com", data))
        self.assertEqual(len(jobs), 1)
        self.assertIn(jobs[0].evidence[0].quote, json.dumps(data))

    def test_optional_json_escapes(self):
        raw = '{"jobs":[{"id":1,"title":"Learning \\u0026 Development","absolute_url":"https://example.com/1","content":"Teach"}]}'
        jobs = normalize(Board("greenhouse", "test", "https://example.com"), response("https://example.com", raw))
        self.assertEqual(jobs[0].title, "Learning & Development")
        self.assertIn(jobs[0].evidence[0].quote, raw)


if __name__ == "__main__":
    unittest.main()
