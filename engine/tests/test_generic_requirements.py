import unittest
from jobrouter.models import Brief, Job, Evidence, now
from jobrouter.matching import screen, apply_review


class GenericRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.brief = Brief("Find UK contracts explicitly outside IR35", requirements=[{
            "id": "outside_ir35", "description": "Must explicitly be outside IR35", "source": "prompt", "source_quote": "explicitly outside IR35"}])
        self.job = Job("fixture", "a", "1", "Data Engineer", "A", "https://example.com/1", "Six month contract, outside IR35.", availability="open")
        self.job.evidence = [Evidence.from_text(self.job.url, self.job.description, "outside IR35", "description"),
                             Evidence.from_text(self.job.url, "<form>", "<form>", "application_form", now())]
        self.review = {"job_id": self.job.identity, "brief_digest": self.brief.digest,
                       "source_digest": self.job.evidence[0].digest, "model": "fixture-reviewer", "relevant": True,
                       "quotes": ["Six month contract"], "score": 95}

    def test_omitted_generic_requirement_stays_conditional(self):
        result = apply_review(screen(self.job, self.brief), self.job, self.review, self.brief)
        self.assertEqual(result.category, "conditional")

    def test_generic_requirement_needs_evidence(self):
        self.review["requirements"] = {"outside_ir35": {"verdict": "pass", "quote": "outside IR35"}}
        result = apply_review(screen(self.job, self.brief), self.job, self.review, self.brief)
        self.assertEqual(result.category, "qualified")
        self.review["requirements"]["outside_ir35"]["quote"] = "Untrue"
        with self.assertRaises(ValueError):
            apply_review(screen(self.job, self.brief), self.job, self.review, self.brief)

    def test_invented_constraint_rejected(self):
        self.brief.requirements[0]["source_quote"] = "must speak Japanese"
        with self.assertRaises(ValueError):
            self.brief.validate()
