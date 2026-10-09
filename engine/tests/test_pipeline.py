import unittest
from jobrouter.models import Brief, now
from jobrouter.pipeline import run_search
from jobrouter.routing import ModelRouter
from jobrouter.transport import PublicFetcher, Response
import json


class PipelineTests(unittest.TestCase):
    def test_full_fixture_pipeline(self):
        title = "Learning Designer"
        def wire(url):
            if url.endswith("robots.txt"):
                data = ""
            elif "questions=true" in url:
                data = json.dumps({"id": 1, "title": title, "absolute_url": "https://job-boards.greenhouse.io/test/jobs/1", "questions": [{"fields": [{"name": "email"}, {"name": "first_name"}]}]})
            else:
                data = json.dumps({"jobs": [{"id": 1, "title": title, "absolute_url": "https://job-boards.greenhouse.io/test/jobs/1", "content": "Design learning experiences."}]})
            return Response(url, 200, {}, data.encode(), now())
        def model(request):
            p = request["payload"]
            if request["task"] == "extractor":
                output = {"job_id": p["job_id"], "facts": {}}
            else:
                output = {"job_id": p["job_id"], "brief_digest": p["brief_digest"],
                          "source_digest": p["job"]["evidence"][-1]["digest"], "relevant": True,
                          "score": 90, "quotes": ["Design learning experiences."], "reasons": ["Fixture duties fit"]}
            return {"actual_model": "fixture-model-not-live", "output": output}
        brief = Brief("Find learning jobs", role_families=["learning"], count=1)
        result = run_search(brief.prompt, None, ["https://job-boards.greenhouse.io/test"],
                            ModelRouter(callback=model), PublicFetcher(wire=wire, per_origin_delay=0), compiled_brief=brief)
        self.assertEqual(result.status, "sufficient_verified_results")
        self.assertEqual(len(result.qualified), 1)
        self.assertEqual(result.coverage["model_calls"], 2)

    def test_mismatched_compiled_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            run_search("Find jobs", None, [], ModelRouter(), PublicFetcher(), compiled_brief=Brief("Other prompt"))
