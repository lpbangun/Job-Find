import unittest
from jobrouter.models import Job
from jobrouter.identity import canonical_job_id, deduplicate


class IdentityTests(unittest.TestCase):
    def test_tracking_url_same_job(self):
        a = canonical_job_id("https://job-boards.greenhouse.io/company/jobs/123?gh_src=xyz")
        b = canonical_job_id("https://boards.greenhouse.io/company/jobs/123")
        self.assertEqual(a, b)

    def test_company_not_excluded(self):
        a = Job("greenhouse", "a", "1", "Designer", "A", "https://job-boards.greenhouse.io/a/jobs/1", "One")
        b = Job("greenhouse", "a", "2", "Trainer", "A", "https://job-boards.greenhouse.io/a/jobs/2", "Two")
        kept, rejected, uncertain = deduplicate([a, b], [a.identity])
        self.assertEqual([x.identity for x in kept], [b.identity])

    def test_equivalent_new_id_is_not_automatically_fresh(self):
        a = Job("greenhouse", "a", "1", "Designer", "A", "https://job-boards.greenhouse.io/a/jobs/1", "Same description")
        b = Job("greenhouse", "a", "2", "Designer", "A", "https://job-boards.greenhouse.io/a/jobs/2", "Same description")
        kept, rejected, uncertain = deduplicate([a, b])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(uncertain), 1)
