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

    def test_known_scalar_conflict_is_atomic(self):
        self.job.arrangement = "onsite"
        with self.assertRaisesRegex(ModelError, "Source fact conflict"):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {
                "salary_min": {"value": 60000, "quote": "$60,000"},
                "arrangement": {"value": "remote", "quote": "Remote"}}})
        self.assertEqual(self.job.arrangement, "onsite")
        self.assertIsNone(self.job.salary_min)
        self.assertEqual(self.job.evidence, [])

    def test_country_scope_cannot_expand_or_shrink(self):
        self.job.countries = ["GB"]
        for values in (["GB", "US"], ["US"], []):
            with self.assertRaisesRegex(ModelError, "Source fact conflict"):
                apply_facts(self.job, {"job_id": self.job.identity, "facts": {
                    "countries": {"value": values, "quote": "US"}}})
        self.assertEqual(self.job.countries, ["GB"])

    def test_required_skills_cannot_remove_known_requirement(self):
        self.job.required_skills = ["SQL"]
        with self.assertRaisesRegex(ModelError, "Source fact conflict"):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {
                "required_skills": {"value": [], "quote": "Remote"}}})
        apply_facts(self.job, {"job_id": self.job.identity, "facts": {
            "required_skills": {"value": ["SQL", "Python"], "quote": "Remote"}}})
        self.assertEqual(self.job.required_skills, ["SQL", "Python"])

    def test_zero_known_fact_is_not_missing(self):
        self.job.experience_min = 0
        with self.assertRaisesRegex(ModelError, "Source fact conflict"):
            apply_facts(self.job, {"job_id": self.job.identity, "facts": {
                "experience_min": {"value": 60000, "quote": "$60,000"}}})
