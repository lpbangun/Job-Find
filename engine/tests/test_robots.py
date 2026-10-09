import unittest
from jobrouter.robots import RobotsPolicy


class RobotsTests(unittest.TestCase):
    def test_longest_allow_and_tie(self):
        p = RobotsPolicy("User-agent: *\nDisallow: /\nAllow: /jobs\nDisallow: /jobs", "JobRouter")
        self.assertTrue(p.allows("https://example.com/jobs/1"))
        self.assertFalse(p.allows("https://example.com/admin"))

    def test_wildcards_end_query(self):
        p = RobotsPolicy("User-agent: *\nDisallow: /*?token=*\nDisallow: /closed$", "JobRouter")
        self.assertFalse(p.allows("https://example.com/path?token=abc"))
        self.assertFalse(p.allows("https://example.com/closed"))
        self.assertTrue(p.allows("https://example.com/closed/other"))

    def test_specific_agent_and_combined_groups(self):
        p = RobotsPolicy("User-agent: *\nDisallow: /\nUser-agent: jobrouter\nDisallow: /a\nUser-agent: JobRouter\nDisallow: /b\nCrawl-delay: 2", "JobRouter/0.1")
        self.assertTrue(p.allows("https://example.com/jobs"))
        self.assertFalse(p.allows("https://example.com/a"))
        self.assertFalse(p.allows("https://example.com/b"))
        self.assertEqual(p.delay, 2)
