import unittest
from jobrouter.models import Job
from jobrouter.extraction import apply_facts
from jobrouter.routing import ModelError


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.job = Job("x", "x", "1", "Trainer", "Company", "https://example.com/1", "Remote in the US. Base salary $60,000 to $80,000.")

    def test_exact_fact(self):
        apply_facts(self.job, {"job_id": self.job.identity, "facts": {"salary_min": {"value": 60000, "quote": "Base salary $60,000"}}})
        self.assertEqual(self.job.salary_min, 60000)

    def test_invention_and_partial_mutation(self):
        with self.assertRaises(ModelError):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {
                "salary_min": {"value": 60000, "quote": "Base salary $60,000"},
                "sponsorship": {"value": "yes", "quote": "We sponsor visas"}}})
        self.assertIsNone(self.job.salary_min)

    def test_nonnumeric_salary(self):
        for number in (True, float("nan"), float("inf"), -1, "60000"):
            with self.assertRaises(ModelError):
                apply_facts(self.job, {"job_id": self.job.identity, "facts": {"salary_min": {"value": number, "quote": "$60,000"}}})

    def test_readonly_identity(self):
        with self.assertRaises(ModelError):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {"url": {"value": "https://evil.com", "quote": "Remote"}}})

    def test_numeric_claim_must_match_quote(self):
        with self.assertRaises(ModelError):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {"salary_min": {"value": 600000, "quote": "$60,000"}}})
