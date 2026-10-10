import unittest
import sys
import time
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

    def test_command_json_success(self):
        command = [sys.executable, "-c", 'import sys,json; x=json.load(sys.stdin); print(json.dumps({"actual_model":"fixture-host","output":{"task":x["task"]}}))']
        router = ModelRouter(command=command)
        self.assertEqual(router.call("extractor", {})["output"]["task"], "extractor")

    def test_command_bounded_stdout_and_stderr(self):
        for stream in ("stdout", "stderr"):
            router = ModelRouter(command=[sys.executable, "-c", f'import sys; sys.{stream}.write("x" * 1000000)'],
                                 policy=ModelPolicy(max_output_bytes=1000))
            with self.assertRaisesRegex(ModelError, "output too large"):
                router.call("reviewer", {})
            self.assertEqual(router.receipts[0]["status"], "failed")

    def test_command_deadline(self):
        router = ModelRouter(command=[sys.executable, "-c", 'import time; time.sleep(30)'],
                             policy=ModelPolicy(timeout=0.1))
        start = time.monotonic()
        with self.assertRaisesRegex(ModelError, "deadline exceeded"):
            router.call("reviewer", {})
        self.assertLess(time.monotonic() - start, 3)

    def test_invalid_policy_rejected(self):
        for values in ({"max_parallel": 0}, {"max_calls": True}, {"max_output_bytes": -1},
                       {"timeout": float("nan")}, {"timeout": float("inf")}, {"timeout": 0}):
            with self.assertRaises(ValueError):
                ModelPolicy(**values)

    def test_actual_identity_must_be_nonblank_string(self):
        for identity in ("  ", 1, {"name": "model"}):
            with self.assertRaises(ModelError):
                ModelRouter(callback=lambda x: {"actual_model": identity, "output": {}}).call("reviewer", {})

    def test_zero_constraint_requires_provenance(self):
        router = ModelRouter(callback=lambda x: {"actual_model": "fixture", "output": {
            "brief": {"maximum_experience": 0}, "provenance": {}}})
        with self.assertRaisesRegex(ModelError, "Unsupported inferred constraint"):
            compile_brief("Find jobs", None, router)

    def test_malformed_planner_contracts_rejected(self):
        for output in ({"brief": []}, {"brief": {}, "provenance": []},
                       {"brief": {"unknown": 1}},
                       {"brief": {"country": "UK"}, "provenance": {"country": []}},
                       {"brief": {"country": "UK"}, "provenance": {"country": {"source": "prompt", "quote": 7}}},
                       {"brief": {"unresolved": "conflict"}},
                       {"brief": {"requirements": [None]}},
                       {"brief": {"requirements": None}},
                       {"brief": {"country": 1}, "provenance": {"country": {"source": "prompt", "quote": "Find"}}},
                       {"brief": {"currency": None}},
                       {"brief": {"needs_sponsorship": "false"}, "provenance": {"needs_sponsorship": {"source": "prompt", "quote": "Find"}}},
                       {"brief": {"requirements": [{"id": ["x"]}]}},
                       {"brief": {"arrangements": "remote"}, "provenance": {"arrangements": {"source": "prompt", "quote": "Find"}}},
                       {"brief": {"count": True}, "provenance": {"count": {"source": "prompt", "quote": "Find"}}}):
            with self.subTest(output=output), self.assertRaises(ModelError):
                router = ModelRouter(callback=lambda request: {"actual_model": "fixture", "output": output})
                compile_brief("Find UK jobs", None, router)

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
