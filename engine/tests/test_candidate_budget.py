"""Known hard failures must not crowd viable/unknown candidates out of review."""
import unittest
from unittest.mock import patch
from jobrouter.discovery import DiscoveryResult
from jobrouter.models import Brief, Evidence, Job
from jobrouter.pipeline import run_search
from jobrouter.routing import ModelRouter
from jobrouter.transport import PublicFetcher


class CandidateBudgetTests(unittest.TestCase):
    def job(self, ident, arrangement):
        job = Job('fixture', 'example', ident, 'Software Engineer', 'Example',
                  'https://example.com/' + ident, 'Build backend software services. Requisition ' + ident, arrangement=arrangement)
        job.evidence.append(Evidence.from_text(job.url, job.description, job.description, 'description'))
        return job

    def run_mission(self, jobs, limit, brief=None, extracted_facts=None):
        calls = []
        def model(request):
            calls.append(request['payload']['job_id'])
            p = request['payload']
            if request['task'] == 'extractor':
                output = {'job_id': p['job_id'], 'facts': extracted_facts or {}}
            else:
                output = {'job_id': p['job_id'], 'brief_digest': p['brief_digest'],
                          'source_digest': p['job']['evidence'][0]['digest'], 'relevant': True,
                          'score': 90, 'quotes': ['Build backend software services.'], 'reasons': ['Fixture fit']}
            return {'actual_model': 'fixture-not-live', 'output': output}
        brief = brief or Brief('Find remote engineering roles', role_families=['engineering'], arrangements=['remote'], count=1)
        with patch('jobrouter.pipeline.discover', return_value=DiscoveryResult(jobs={job.identity: job for job in jobs})), \
             patch('jobrouter.pipeline.verify_application', return_value={'status': 'unverified', 'reason': 'Fixture has no verified form'}):
            result = run_search(brief.prompt, None, [], ModelRouter(callback=model), PublicFetcher(),
                                candidate_limit=limit, compiled_brief=brief)
        return result, calls

    def test_known_failure_does_not_consume_only_review_slot(self):
        bad, viable = self.job('0-onsite', 'onsite'), self.job('1-remote', 'remote')
        result, calls = self.run_mission([bad, viable], 1)
        self.assertEqual(calls, [viable.identity, viable.identity])
        self.assertEqual(len(result.excluded), 1)
        self.assertEqual(result.excluded[0]['job']['external_id'], '0-onsite')
        self.assertTrue(any(c['criterion'] == 'arrangement' and c['verdict'] == 'fail' for c in result.excluded[0]['decision']['checks']))
        self.assertEqual(result.coverage['collected'], 2)
        self.assertEqual(result.coverage['excluded_before_review'], 1)
        self.assertEqual(result.coverage['review_candidates'], 1)
        self.assertEqual(result.coverage['not_reviewed_due_to_limit'], 0)
        self.assertFalse(result.qualified, 'Unverified application must remain conditional')
        self.assertEqual(len(result.conditional), 1)

    def test_unknown_facts_are_still_reviewed_and_never_promoted(self):
        result, calls = self.run_mission([self.job('0-unknown', 'unknown')], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.coverage['excluded_before_review'], 0)
        self.assertEqual(len(result.conditional), 1)
        self.assertFalse(result.qualified)

    def test_all_hard_failures_need_no_model_calls(self):
        result, calls = self.run_mission([self.job('0-onsite', 'onsite'), self.job('1-hybrid', 'hybrid')], 1)
        self.assertFalse(calls)
        self.assertEqual(len(result.excluded), 2)
        self.assertEqual(result.coverage['review_candidates'], 0)
        self.assertEqual(result.coverage['not_reviewed_due_to_limit'], 0)
        self.assertEqual(result.status, 'shortfall')

    def test_remaining_eligible_omissions_are_reported(self):
        result, _ = self.run_mission([self.job('0-onsite', 'onsite'), self.job('1-remote', 'remote'), self.job('2-unknown', 'unknown')], 1)
        self.assertEqual(result.coverage['excluded_before_review'], 1)
        self.assertEqual(result.coverage['not_reviewed_due_to_limit'], 1)

    def test_unknown_arrangement_location_failure_can_be_resolved_by_extraction(self):
        job = self.job('0-location', 'unknown')
        job.location = 'New York'
        job.description += '. Remote work is available.'
        job.evidence = [Evidence.from_text(job.url, job.description, job.description, 'description')]
        brief = Brief('Find London or remote jobs', locations=['London'])
        result, calls = self.run_mission([job], 1, brief,
            {'arrangement': {'value': 'remote', 'quote': 'Remote work is available.'}})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.coverage['excluded_before_review'], 0)
        self.assertEqual(len(result.conditional), 1)
        self.assertFalse(result.qualified)

    def test_unresolved_location_failure_still_excluded_after_extraction(self):
        job = self.job('0-location', 'unknown')
        job.location = 'New York'
        result, calls = self.run_mission([job], 1, Brief('Find London jobs', locations=['London']))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.coverage['excluded_before_review'], 0)
        self.assertEqual(len(result.excluded), 1)
        self.assertFalse(result.qualified)
