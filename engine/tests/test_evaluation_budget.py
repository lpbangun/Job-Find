"""Offline synthetic reservation/manifest tests, not a live evaluation."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from jobrouter.evaluation_budget import EvaluationBudget, EvaluationBudgetError, validate_development_manifest
from jobrouter.transport import PublicFetcher, Response
from jobrouter.routing import ModelRouter
from jobrouter.browser_verification import BrowserApplicationVerifier, BrowserPolicy
from jobrouter.pipeline import run_search
from jobrouter.discovery import DiscoveryResult
from jobrouter.models import Brief, Job


class SharedBudgetTests(unittest.TestCase):
    def test_parallel_reservations_are_atomic(self):
        budget = EvaluationBudget({'http_attempts': 7})
        def reserve(_):
            try:
                budget.reserve({'http_attempts': 1}, 'fixture')
                return True
            except EvaluationBudgetError:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(reserve, range(60))), 7)
        snapshot = budget.snapshot()
        self.assertEqual(snapshot['reserved']['http_attempts'], 7)
        self.assertEqual(len(snapshot['events']), 60)

    def test_multicharge_denial_does_not_partially_debit(self):
        budget = EvaluationBudget({'search_calls': 2, 'http_attempts': 1})
        with self.assertRaises(EvaluationBudgetError):
            budget.reserve({'search_calls': 1, 'http_attempts': 2}, 'search')
        self.assertEqual(budget.snapshot()['reserved'], {'search_calls': 0, 'http_attempts': 0})

    def test_failures_and_robots_share_across_fetchers(self):
        seen = []
        def wire(url):
            seen.append(url)
            if url.endswith('/robots.txt'):
                return Response(url, 200, {}, b'User-agent: *\nAllow: /', 'fixture')
            raise RuntimeError('fixture failure')
        budget = EvaluationBudget({'http_attempts': 3})
        first = PublicFetcher(wire=wire, per_origin_delay=0, shared_budget=budget)
        second = PublicFetcher(wire=wire, per_origin_delay=0, shared_budget=budget)
        with self.assertRaises(RuntimeError):
            first.get('https://example.com/a')
        with self.assertRaises(EvaluationBudgetError):
            second.get('https://example.org/b')
        self.assertEqual(len(seen), 3)
        self.assertEqual(budget.snapshot()['reserved']['http_attempts'], 3)

    def test_routers_share_ceiling_before_callback(self):
        calls = []
        def callback(request):
            calls.append(request)
            return {'output': {}, 'actual_model': 'fixture-model'}
        budget = EvaluationBudget({'model_calls': 1})
        first = ModelRouter(callback=callback, shared_budget=budget)
        second = ModelRouter(callback=callback, shared_budget=budget)
        first.call('planner', {})
        with self.assertRaises(EvaluationBudgetError):
            second.call('reviewer', {})
        self.assertEqual(len(calls), 1)

    def test_browser_reserves_full_worker_allowance_without_refund(self):
        budget = EvaluationBudget({'http_attempts': 5})
        browser = BrowserApplicationVerifier(BrowserPolicy(('example.com',), request_budget=4), shared_budget=budget)
        with patch('jobrouter.browser_verification._run_host', return_value={'error': 'fixture'}) as worker:
            browser._capture({}, 1, 'fixture-nonce')
            with self.assertRaises(EvaluationBudgetError):
                browser._capture({}, 1, 'fixture-nonce')
            self.assertEqual(worker.call_count, 1)
        fetcher = PublicFetcher(wire=lambda u: Response(u, 200, {}, b'', 'fixture'), per_origin_delay=0, shared_budget=budget)
        fetcher._one('https://example.com/a')
        with self.assertRaises(EvaluationBudgetError):
            fetcher._one('https://example.com/b')
        self.assertEqual(budget.snapshot()['reserved']['http_attempts'], 5)

    def test_expired_deadline_prevents_dispatch(self):
        tick = [0]
        budget = EvaluationBudget({'model_calls': 1}, seconds=1, clock=lambda: tick[0])
        tick[0] = 1
        called = []
        router = ModelRouter(callback=lambda r: called.append(r), shared_budget=budget)
        with self.assertRaises(EvaluationBudgetError):
            router.call('planner', {})
        self.assertEqual(called, [])
        self.assertEqual(budget.snapshot()['reserved']['model_calls'], 0)

    def test_snapshot_cannot_mutate_ledger(self):
        budget = EvaluationBudget({'model_calls': 1})
        budget.reserve({'model_calls': 1}, 'fixture')
        snapshot = budget.snapshot()
        snapshot['reserved']['model_calls'] = 0
        snapshot['events'][0]['charges']['model_calls'] = 0
        self.assertEqual(budget.snapshot()['reserved']['model_calls'], 1)
        self.assertEqual(budget.snapshot()['events'][0]['charges']['model_calls'], 1)

    def test_pipeline_rejects_unshared_components_before_any_dispatch(self):
        budget = EvaluationBudget({'http_attempts': 1, 'model_calls': 1, 'candidates': 1})
        router = ModelRouter(callback=lambda _: self.fail('Must not dispatch'), shared_budget=budget)
        fetcher = PublicFetcher(wire=lambda _: self.fail('Must not dispatch'))
        with self.assertRaisesRegex(ValueError, 'same shared budget'):
            run_search('synthetic', None, [], router, fetcher)
        fetcher.shared_budget = budget
        browser = BrowserApplicationVerifier(BrowserPolicy(('example.com',)))
        with self.assertRaisesRegex(ValueError, 'same shared budget'):
            run_search('synthetic', None, [], router, fetcher, browser_provider=browser)
        self.assertEqual(budget.snapshot()['events'], [])

    def test_pipeline_rejects_differing_nonnull_ledgers(self):
        first = EvaluationBudget({'http_attempts': 1, 'model_calls': 1, 'candidates': 1})
        second = EvaluationBudget({'http_attempts': 1, 'model_calls': 1, 'candidates': 1})
        router = ModelRouter(callback=lambda _: self.fail('Must not dispatch'), shared_budget=first)
        fetcher = PublicFetcher(wire=lambda _: self.fail('Must not dispatch'), shared_budget=second)
        with self.assertRaisesRegex(ValueError, 'same shared budget'):
            run_search('synthetic', None, [], router, fetcher)
        fetcher.shared_budget = first
        browser = BrowserApplicationVerifier(BrowserPolicy(('example.com',)), shared_budget=second)
        with self.assertRaisesRegex(ValueError, 'same shared budget'):
            run_search('synthetic', None, [], router, fetcher, browser_provider=browser)
        self.assertEqual(first.snapshot()['events'], [])
        self.assertEqual(second.snapshot()['events'], [])

    def test_exhausted_candidate_budget_prevents_extraction_and_keeps_shortfall(self):
        budget = EvaluationBudget({'http_attempts': 1, 'model_calls': 1, 'candidates': 1})
        budget.reserve({'candidates': 1}, 'prior_fixture_review')
        router = ModelRouter(callback=lambda _: self.fail('Must not dispatch'), shared_budget=budget)
        fetcher = PublicFetcher(wire=lambda _: self.fail('Must not dispatch'), shared_budget=budget)
        job = Job('fixture', 'example', '1', 'Software Engineer', 'Example',
                  'https://example.com/1', 'Build backend software.')
        brief = Brief('Find software roles', count=1)
        with patch('jobrouter.pipeline.discover', return_value=DiscoveryResult(jobs={job.identity: job})), \
             patch('jobrouter.pipeline.extract_facts') as extract, \
             patch('jobrouter.pipeline.verify_application') as verify:
            result = run_search(brief.prompt, None, [], router, fetcher, compiled_brief=brief)
        extract.assert_not_called()
        verify.assert_not_called()
        self.assertFalse(result.qualified)
        self.assertEqual(result.status, 'shortfall')
        self.assertEqual(len(result.conditional), 1)
        self.assertIn('Shared candidates budget exhausted', result.errors[0]['error'])
        self.assertEqual(result.coverage['model_calls'], 0)
        self.assertEqual(result.coverage['shortfall'], 1)
        snapshot = budget.snapshot()
        self.assertEqual(snapshot['reserved']['candidates'], 1)
        self.assertEqual(snapshot['events'][-1]['status'], 'denied')

    def test_invalid_limits_and_charges(self):
        for limits in ({}, {'a': True}, {'a': 0}, {'a': 1.5}):
            with self.assertRaises(ValueError): EvaluationBudget(limits)
        budget = EvaluationBudget({'a': 2})
        for charges in ({}, {'a': True}, {'a': -1}, {'other': 1}):
            with self.assertRaises(ValueError): budget.reserve(charges, 'fixture')
        self.assertEqual(budget.snapshot()['reserved']['a'], 0)


class ManifestTests(unittest.TestCase):
    def manifest(self):
        capabilities = ('shared_budget', 'model_token_cap', 'served_model_provenance',
                        'accounted_search', 'shared_origin_pacing', 'shared_concurrency',
                        'interruptible_deadline', 'independent_judges')
        return {'split': 'development', 'synthetic_profiles': True,
                'arms': ['jobfind', 'standalone_web_search'], 'brief_ids': ['D39', 'D38', 'D40'],
                'protocol_sha256': 'a'*64, 'source_sha256': 'b'*64,
                'inputs_sha256': 'c'*64, 'configuration_sha256': 'd'*64,
                'served_models': ['synthetic-version-1'],
                'limits': {'seconds': 900, 'search_calls': 20, 'http_attempts': 120,
                           'candidates': 60, 'model_calls': 121, 'model_tokens': 200000,
                           'parallel': 4, 'origin_delay_seconds': 1},
                'verified_capabilities': {k: True for k in capabilities},
                'capability_evidence_sha256': {k: 'e'*64 for k in capabilities}}

    def test_declared_synthetic_manifest_structure(self):
        manifest = self.manifest()
        result = validate_development_manifest(manifest)
        result['brief_ids'].append('D01')
        self.assertEqual(len(manifest['brief_ids']), 3)

    def test_heldout_private_or_missing_inputs_rejected(self):
        for key, value in [('split', 'heldout'), ('synthetic_profiles', False),
                           ('brief_ids', ['H01']), ('brief_ids', ['D01', 'D01']),
                           ('brief_ids', [{}]), ('protocol_sha256', ''),
                           ('served_models', ['unknown']), ('served_models', ['strong'])]:
            manifest = self.manifest(); manifest[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_development_manifest(manifest)

    def test_missing_capability_or_evidence_blocks_execution(self):
        for field in ('verified_capabilities', 'capability_evidence_sha256'):
            manifest = self.manifest(); manifest[field].pop('accounted_search')
            with self.assertRaises(ValueError): validate_development_manifest(manifest)
        manifest = self.manifest(); manifest['limits']['http_attempts'] = 121
        with self.assertRaises(ValueError): validate_development_manifest(manifest)
