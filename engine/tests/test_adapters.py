import json
import unittest
from jobrouter.adapters import Board, normalize
from jobrouter.transport import Response
from jobrouter.models import now


def parse(provider, payload):
    return normalize(Board(provider, "company", "https://example.com"), Response("https://example.com", 200, {}, json.dumps(payload).encode(), now()))


class AdapterTests(unittest.TestCase):
    def test_ashby_unlisted_and_remote(self):
        rows = [{"id": "1", "title": "Designer", "jobUrl": "https://jobs.ashbyhq.com/company/1", "descriptionPlain": "Design", "isRemote": True, "employmentType": "FullTime"},
                {"id": "2", "isListed": False}]
        jobs = parse("ashby", {"jobs": rows})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].arrangement, "remote")
        self.assertEqual(jobs[0].employment, "full-time")

    def test_lever_lists_not_dropped(self):
        jobs = parse("lever", [{"id": "1", "text": "Trainer", "hostedUrl": "https://jobs.lever.co/company/1", "description": "Role", "lists": [{"text": "Requirements", "content": "<li>Mandatory SQL</li>"}], "categories": {"location": "Paris", "commitment": "Full-time"}}])
        self.assertIn("Mandatory SQL", jobs[0].description)
        self.assertEqual(jobs[0].location, "Paris")

    def test_workable_separate_location_fields(self):
        jobs = parse("workable", {"jobs": [{"shortcode": "ABC", "title": "Engineer", "shortlink": "https://apply.workable.com/j/ABC", "city": "Paris", "country": "France", "telecommuting": True}]})
        self.assertEqual(jobs[0].location, "Paris, France")
        self.assertEqual(jobs[0].arrangement, "remote")

    def test_recruitee_unpublished_skipped(self):
        jobs = parse("recruitee", {"offers": [{"id": "1", "title": "Trainer", "careers_url": "https://company.recruitee.com/o/trainer", "status": "published", "employment_type_code": "part_time"}, {"status": "draft"}]})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].employment, "part-time")

    def test_conflicting_duplicate_not_silently_dropped(self):
        rows = [{"id": "1", "title": x, "absolute_url": "https://job-boards.greenhouse.io/company/jobs/1"} for x in ("Trainer", "Developer")]
        with self.assertRaises(ValueError):
            parse("greenhouse", {"jobs": rows})
