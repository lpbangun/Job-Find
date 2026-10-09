"""Offline regressions: form evidence must be enabled, scoped and job-bound."""
import json
import unittest

from jobrouter.models import Job, now
from jobrouter.transport import Response
from jobrouter.verification import verify_application


class FixtureFetcher:
    def __init__(self, html):
        self.html = html
        self.requests = []

    def get(self, url):
        self.requests.append(url)
        return Response(url, 200, {}, self.html.encode(), now())


class ApplicationFormTests(unittest.TestCase):
    fields = '<input name="full_name"><input type="email" name="email">'
    submit = '<button type="submit">Submit application</button>'

    def form(self, fields=None, submit=None, action='/jobs/123/apply', extra=''):
        return f'<form action="{action}" {extra}>{self.fields if fields is None else fields}{self.submit if submit is None else submit}</form>'

    def check(self, html, expected='unverified', provider='structured'):
        job = Job(provider, 'example', '123', 'Learning Designer', 'Example',
                  'https://careers.example.com/jobs/123', 'Design courses')
        fetcher = FixtureFetcher('<h1>Learning Designer</h1>' + html)
        result = verify_application(job, fetcher)
        self.assertEqual(result['status'], expected, result)
        self.assertEqual(job.availability, expected)
        self.assertEqual(len(fetcher.requests), 1)
        self.assertEqual(len(job.evidence), int(expected == 'open'))
        return job

    def test_job_bound_application_form(self):
        job = self.check(self.form(), 'open')
        self.assertEqual(job.apply_url, job.url)
        self.assertEqual(job.evidence[0].field, 'application_form')

    def test_known_hidden_job_binding(self):
        self.check(self.form(fields=self.fields + '<input type="hidden" name="job_id" value="123">', action='/apply'), 'open')
        self.check(self.form(fields=self.fields + '<input type="hidden" name="positionId" value="123">', action=''), 'open')

    def test_newsletter_contact_and_signup_are_not_applications(self):
        for intent in ('Newsletter', 'Contact us', 'Sign up', 'Subscribe'):
            with self.subTest(intent=intent):
                self.check(self.form(submit=f'<button>{intent}</button>'))
                self.check(self.form(extra=f'aria-label="{intent}"'))

    def test_contact_fields_and_optional_newsletter_do_not_override_application_intent(self):
        self.check(self.form(fields='<h2>Contact information</h2>' + self.fields +
                             '<label><input type="checkbox" name="updates">Optional job newsletter</label>'), 'open')

    def test_hidden_or_aria_disabled_controls_do_not_establish_usable_form(self):
        for attribute in ('hidden', 'aria-disabled="true"', 'inert'):
            with self.subTest(attribute=attribute):
                self.check(self.form(fields=f'<input name="full_name"><input type="email" name="email" {attribute}>'))
                self.check(self.form(submit=f'<button {attribute}>Apply</button>'))
                self.check(f'<div {attribute}>' + self.form() + '</div>')
                self.check(self.form(fields=f'<div {attribute}><div>' + self.fields + '</div></div>'))

    def test_inline_hidden_controls_and_ancestors_are_rejected(self):
        for style in ('display:none', ' DISPLAY : NONE !IMPORTANT ',
                      'color: red; visibility : hidden ! important;',
                      'visibility:COLLAPSE', 'display:/**/none'):
            with self.subTest(style=style):
                attribute = f'style="{style}"'
                self.check(self.form(fields=f'<input name="full_name"><input type="email" name="email" {attribute}>'))
                self.check(self.form(submit=f'<button {attribute}>Apply</button>'))
                self.check(f'<div {attribute}>' + self.form() + '</div>')
                self.check(self.form(fields=f'<div {attribute}><div>' + self.fields + '</div></div>'))
        self.check(self.form(extra='style="display:block; visibility:visible"'), 'open')

    def test_conflicting_hidden_job_id_vetoes_other_identity_evidence(self):
        wrong = '<input type="hidden" name="job_id" value="999">'
        matching = '<input type="hidden" name="position_id" value="123">'
        self.check(self.form(fields=self.fields + wrong))
        self.check(self.form(fields=self.fields + matching + wrong))
        self.check(self.form(fields=self.fields + matching + wrong, action='/apply'))
        self.check(self.form(fields=self.fields + wrong.replace('value="999"', 'value="999" disabled')))
        self.check(self.form(fields=self.fields + wrong.replace('value="999"', 'value=""')), 'open')

    def test_email_in_different_form_is_not_borrowed(self):
        self.check(self.form(fields='<input name="full_name">') + '<form><input type="email" name="email"></form>')

    def test_disabled_controls_and_fieldsets(self):
        for html in (
            self.form(extra='disabled'),
            self.form(fields='<input name="full_name" disabled><input type="email" name="email">'),
            self.form(fields='<input name="full_name"><input type="email" name="email" disabled>'),
            self.form(submit='<button disabled>Apply</button>'),
            self.form(fields='<fieldset disabled>' + self.fields + '</fieldset>'),
            self.form(submit='<fieldset disabled><button>Apply</button></fieldset>'),
            '<fieldset disabled>' + self.form() + '</fieldset>',
            self.form(fields='<fieldset disabled><fieldset>' + self.fields + '</fieldset></fieldset>'),
        ):
            with self.subTest(html=html):
                self.check(html)

    def test_comment_script_style_and_template_forms_are_ignored(self):
        for start, end in (('<!--', '-->'), ('<script>', '</script>'), ('<style>', '</style>'), ('<template>', '</template>')):
            with self.subTest(start=start):
                self.check(start + self.form() + end)
        self.check(self.form(fields='<!--' + self.fields + '-->'))

    def test_generic_and_wrong_job_forms_do_not_establish_identity(self):
        for action in ('/apply', '/jobs/1234/apply', '/jobs/123-else/apply', '/apply?job_id=123', ''):
            with self.subTest(action=action):
                self.check(self.form(action=action))
        for field in ('<input type="hidden" name="job_id" value="124">',
                      '<input type="hidden" name="id" value="123">',
                      '<input type="hidden" name="job_id" value="123" disabled>'):
            self.check(self.form(fields=self.fields + field, action='/apply'))

    def test_malicious_actions_are_rejected_even_with_hidden_binding(self):
        for action in ('https://evil.example/jobs/123', '//evil.example/jobs/123',
                       'javascript:alert(123)', 'http://careers.example.com/jobs/123',
                       'https://user:password@careers.example.com/jobs/123',
                       'https://127.0.0.1/jobs/123', '/jobs/%2e%2e/123'):
            with self.subTest(action=action):
                self.check(self.form(action=action, fields=self.fields + '<input type="hidden" name="job_id" value="123">'))
        self.check(self.form(submit='<button formaction="https://evil.example/jobs/123">Apply</button>'))
        self.check('<base href="https://evil.example/">' + self.form())

    def test_no_enabled_application_submit(self):
        for submit in ('', '<button type="button">Apply</button>', '<input type="submit" value="Send">'):
            self.check(self.form(submit=submit))
        self.check(self.form(submit='<input type="submit" value="Apply now">'), 'open')

    def test_explicit_other_form_ownership_is_not_borrowed(self):
        self.check(self.form(fields='<input name="full_name"><input type="email" name="email" form="newsletter">'))
        self.check(self.form(submit='<button form="newsletter">Apply</button>'))

    def test_title_inside_comment_is_not_visible_identity(self):
        job = Job('structured', 'example', '123', 'Learning Designer', 'Example',
                  'https://careers.example.com/jobs/123', 'Design courses')
        result = verify_application(job, FixtureFetcher('<!--Learning Designer-->' + self.form()))
        self.assertEqual(result['status'], 'unverified')

    def test_greenhouse_exact_schema_stays_read_only(self):
        job = Job('greenhouse', 'example', '123', 'Learning Designer', 'Example',
                  'https://job-boards.greenhouse.io/example/jobs/123', 'Design courses')
        schema = {'id': 123, 'title': job.title, 'absolute_url': job.url,
                  'questions': [{'fields': [{'name': 'email'}, {'name': 'first_name'}]}]}
        fetcher = FixtureFetcher(json.dumps(schema))
        result = verify_application(job, fetcher)
        self.assertEqual(result['status'], 'open')
        self.assertEqual(fetcher.requests, ['https://boards-api.greenhouse.io/v1/boards/example/jobs/123?questions=true'])
        for key, value in (('id', 124), ('title', 'Other job'), ('absolute_url', 'https://evil.example/jobs/123'), ('questions', [])):
            with self.subTest(key=key):
                bad = dict(schema, **{key: value})
                self.assertEqual(verify_application(job, FixtureFetcher(json.dumps(bad)))['status'], 'unverified')
