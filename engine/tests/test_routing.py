import unittest
from jobrouter.routing import ModelRouter, ModelPolicy, ModelError, compile_brief


class RoutingTests(unittest.TestCase):
    def test_missing_runtime_is_blocked(self):
        with self.assertRaises(ModelError):
            ModelRouter().call("planner", {})

    def test_actual_identity_required(self):
        router = ModelRouter(callback=lambda x: {"output": {}})
        with self.assertRaises(ModelError):
            router.call("reviewer", {})
        self.assertEqual(router.receipts[0]["status"], "failed")

    def test_budget_and_routing(self):
        router = ModelRouter(policy=ModelPolicy(max_calls=1), callback=lambda x: {"actual_model": "fixture-fast", "output": {}})
        router.call("extractor", {})
        with self.assertRaises(ModelError):
            router.call("reviewer", {})
        self.assertEqual(router.receipts[0]["requested_model"], "fast")
        self.assertEqual(router.receipts[0]["actual_model"], "fixture-fast")

    def test_profile_cannot_leak_into_no_profile_brief(self):
        router = ModelRouter(callback=lambda x: {"actual_model": "fixture-planner", "output": {
            "brief": {"country": "US"}, "provenance": {"country": {"source": "profile", "quote": "US"}}}})
        with self.assertRaises(ModelError):
            compile_brief("Find jobs in India", None, router)

    def test_prompt_bound_brief(self):
        router = ModelRouter(callback=lambda x: {"actual_model": "fixture-planner", "output": {
            "brief": {"arrangements": ["remote"]}, "provenance": {"arrangements": {"source": "prompt", "quote": "remote"}}}})
        brief, meta = compile_brief("Find remote jobs", None, router)
        self.assertEqual(brief.arrangements, ["remote"])
        self.assertIsNone(brief.profile)


if __name__ == "__main__":
    unittest.main()
