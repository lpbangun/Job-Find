"""Synthetic metric integrity regressions, not relevance benchmark evidence."""
import unittest

from jobrouter.evaluation import evaluate


class EvaluationCompletenessTests(unittest.TestCase):
    def test_omitted_reference_case_is_not_silently_dropped(self):
        result = evaluate({"easy": ["a"]}, {"easy": ["a"], "hard": ["b"]}, required_count=1)
        rows = {row["case"]: row for row in result["cases"]}
        self.assertEqual(set(rows), {"easy", "hard"})
        self.assertEqual(rows["hard"]["returned"], 0)
        self.assertIsNone(rows["hard"]["precision"])
        self.assertEqual(rows["hard"]["recall"], 0)
        self.assertFalse(rows["hard"]["pass"])
        self.assertFalse(result["all_case_targets_met"])
        self.assertEqual(result["macro_strict_precision_at_k"], .5)
        # Missing output changes coverage, not precision among returned entries.
        self.assertEqual(result["micro_precision"], 1)

    def test_entirely_missing_run_retains_reference_cases(self):
        result = evaluate({}, {"a": ["1"], "b": ["2"]})
        self.assertEqual(len(result["cases"]), 2)
        self.assertIsNone(result["micro_precision"])
        self.assertEqual(result["macro_strict_precision_at_k"], 0)
        self.assertFalse(result["all_case_targets_met"])

    def test_result_without_reference_still_fails(self):
        result = evaluate({"a": ["1"], "unjudged": ["2"]}, {"a": ["1"]}, required_count=1)
        self.assertEqual(len(result["cases"]), 2)
        self.assertFalse(result["all_case_targets_met"])

    def test_explicit_empty_and_missing_results_have_same_metrics(self):
        references = {"a": ["1"], "b": ["2"]}
        self.assertEqual(evaluate({"a": ["1"]}, references),
                         evaluate({"a": ["1"], "b": []}, references))

    def test_synthetic_perfect_score_never_sets_release_pass(self):
        result = evaluate({"a": ["1"]}, {"a": ["1"]}, required_count=1)
        self.assertTrue(result["all_case_targets_met"])
        self.assertFalse(result["release_pass"])

    def test_empty_mappings_do_not_pass(self):
        result = evaluate({}, {})
        self.assertEqual(result["cases"], [])
        self.assertIsNone(result["micro_precision"])
        self.assertIsNone(result["macro_strict_precision_at_k"])
        self.assertFalse(result["all_case_targets_met"])

    def test_omitted_empty_reference_is_retained_without_success_claim(self):
        result = evaluate({}, {"unknown_opportunity": []})
        self.assertEqual(len(result["cases"]), 1)
        self.assertIsNone(result["cases"][0]["recall"])
        self.assertFalse(result["cases"][0]["pass"])

    def test_reference_limited_target_does_not_certify_top_ten(self):
        result = evaluate({"scarce": ["1"]}, {"scarce": ["1"]})
        self.assertTrue(result["all_case_targets_met"])
        self.assertEqual(result["cases"][0]["strict_precision_at_k"], .1)
        self.assertEqual(result["cases"][0]["shortfall"], 9)
        self.assertFalse(result["release_pass"])
