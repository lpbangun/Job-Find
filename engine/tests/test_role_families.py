import unittest

from jobrouter.matching import retrieval_terms, screen
from jobrouter.models import Brief, Job


class RoleFamilyTests(unittest.TestCase):
    def job(self, title):
        return Job('fixture', 'example', title, title, 'Example', 'https://example.com/job', 'Fixture duties.')

    def test_natural_language_families_retrieve_related_titles(self):
        for family, title in (
            ('software engineering', 'Senior Software Engineer'),
            ('backend software engineering', 'Backend Developer'),
            ('Software Development', 'Software Engineer II'),
            ('front-end engineering', 'Frontend Developer'),
            ('instructional design', 'Curriculum Designer'),
            ('human resources', 'People Operations Coordinator'),
            ('talent acquisition', 'Technical Recruiter'),
            ('customer implementation', 'Implementation Consultant'),
            ('business operations', 'Strategy Associate'),
            ('product design', 'UX Designer'),
            ('business development', 'Account Executive'),
        ):
            with self.subTest(family=family):
                decision = screen(self.job(title), Brief('Find jobs', role_families=[family]))
                self.assertGreater(decision.score, 0)
                self.assertEqual(decision.category, 'conditional')

    def test_synonyms_do_not_duplicate_or_inflate_retrieval_score(self):
        job = self.job('Backend Software Engineer')
        single = screen(job, Brief('Find jobs', role_families=['engineering']))
        aliases = screen(job, Brief('Find jobs', role_families=['software engineering', 'software development', 'engineering']))
        self.assertEqual(single.score, aliases.score)
        self.assertEqual(single.reasons, aliases.reasons)

    def test_related_title_precedes_unrelated_low_identity(self):
        brief = Brief('Find jobs', role_families=['software engineering'])
        unrelated, related = self.job('Account Executive'), self.job('Software Engineer II')
        ordered = sorted([unrelated, related], key=lambda job: (-screen(job, brief).score, job.identity))
        self.assertEqual(ordered[0], related)

    def test_unknown_domains_remain_literal(self):
        self.assertEqual(retrieval_terms(['Civil Engineering']), ['civil engineering'])
        decision = screen(self.job('Software Engineer'), Brief('Find jobs', role_families=['Civil Engineering']))
        self.assertEqual(decision.score, 0)
        self.assertEqual(decision.category, 'conditional')

    def test_acronyms_do_not_match_inside_unrelated_words(self):
        for family, title in (('product design', 'Luxury Sales Associate'),
                              ('people', 'Thrift Store Coordinator'),
                              ('sales', 'Roadsdrain Inspector')):
            with self.subTest(family=family, title=title):
                self.assertEqual(screen(self.job(title), Brief('Find jobs', role_families=[family])).score, 0)
        self.assertGreater(screen(self.job('UX Designer'), Brief('Find jobs', role_families=['product design'])).score, 0)

    def test_hyphen_and_spacing_variants(self):
        for family, titles in (('front-end engineering', ('Front-end Engineer', 'Front End Engineer', 'Frontend Engineer')),
                               ('back-end engineering', ('Back-end Engineer', 'Back End Engineer', 'Backend Engineer')),
                               ('fullstack engineering', ('Full-stack Engineer', 'Full Stack Engineer', 'Fullstack Engineer'))):
            with self.subTest(family=family):
                scores = [screen(self.job(title), Brief('Find jobs', role_families=[family])).score for title in titles]
                self.assertGreater(scores[0], 0)
                self.assertEqual(len(set(scores)), 1)

    def test_explicit_specialty_preferred_without_excluding_other_engineering(self):
        brief = Brief('Find jobs', role_families=['software engineering', 'backend software engineering'])
        backend = screen(self.job('Backend Engineer'), brief)
        frontend = screen(self.job('Frontend Software Engineer Developer'), brief)
        self.assertGreater(backend.score, frontend.score)
        self.assertGreater(frontend.score, 0)
        self.assertEqual(frontend.category, 'conditional')

    def test_specialty_priority_does_not_demote_independent_role_families(self):
        job = self.job('Account Executive Sales Development')
        sales = screen(job, Brief('Find jobs', role_families=['sales']))
        mixed = screen(job, Brief('Find jobs', role_families=['backend engineering', 'sales']))
        self.assertEqual(sales.score, mixed.score)
        self.assertEqual(mixed.category, 'conditional')
