"""Task 6.1: SQL pagination/search without changing write or export scope."""
from datetime import date
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from .views import RESOURCE_MODELS
from .test_known_defects import SchedulingDefectFixture


class AcademicListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('list-admin', password='test')
        cls.departments = [m.Department.objects.create(code=f'D{i:03}', name=f'Department {i:03}') for i in range(45)]

    def setUp(self):
        self.client.force_login(self.admin)

    def get(self, resource='departments', **params):
        return self.client.get(reverse('resource_list', args=[resource]), params)

    def test_record_summary_and_actions_remain_outside_control_scrolling(self):
        response = self.get()
        self.assertContains(response, 'class="panel record-list-panel"')
        self.assertContains(response, 'class="subtle record-summary" role="status"')
        self.assertContains(response, '45 total')
        self.assertContains(response, '45 matching')
        self.assertContains(response, 'Showing 1\u201320')
        self.assertContains(response, 'class="table-wrap record-table-scroll" role="region"')
        self.assertContains(response, 'class="record-actions"', count=20)
        obj = response.context['objects'][0]
        self.assertContains(response, reverse('resource_update', args=['departments', obj.pk]))
        self.assertContains(response, reverse('resource_delete', args=['departments', obj.pk]))
        html = response.content.decode()
        self.assertLess(html.index('record-controls'), html.index('record-table-scroll'))
        self.assertLess(html.index('record-summary'), html.index('record-table-scroll'))

    def test_first_middle_last_and_stable_order(self):
        seen = []
        for number, expected in ((1, 20), (2, 20), (3, 5)):
            response = self.get(page=number, sort='added_asc')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['objects']), expected)
            self.assertContains(response, f'Page {number} of 3')
            seen += [obj.pk for obj in response.context['objects']]
        self.assertEqual(seen, [d.pk for d in self.departments])
        self.assertEqual(len(set(seen)), 45)

    def test_invalid_pages_and_empty_dataset(self):
        for value, expected in (('-1', 1), ('0', 1), ('bad', 1), ('1.5', 1), ('9999', 3)):
            with self.subTest(value=value):
                self.assertEqual(self.get(page=value).context['page_obj'].number, expected)
        response = self.get('rooms', page=999)
        self.assertContains(response, 'No records in this view.')
        self.assertContains(response, 'Page 1 of 1')

    def test_search_partial_case_and_blank(self):
        self.assertEqual(len(self.get(q='dEpArTmEnT 04').context['objects']), 5)
        self.assertEqual(self.get(q='D044').context['objects'][0].pk, self.departments[-1].pk)
        self.assertEqual(self.get(q='  ').context['page_obj'].paginator.count, 45)
        self.assertEqual(self.get(q=' Department 044 ').context['page_obj'].paginator.count, 1)

    def test_literal_special_characters_and_no_html_injection(self):
        m.Department.objects.create(code='SPECIAL', name='100%_Research & <School>')
        response = self.get(q='%_')
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertContains(response, 'SPECIAL')
        self.assertContains(self.get(q='<School>'), '&lt;School&gt;')
        self.assertContains(self.get(q="' OR 1=1 --"), 'No records match your search.')
        self.assertContains(self.get(q='<script>'), '&lt;script&gt;')

    def test_navigation_preserves_query_and_sort_and_header_resets_page(self):
        response = self.get(q='Department', sort='added_asc', page=2)
        params = parse_qs(urlsplit(response.context['pagination']['next']).query)
        self.assertEqual(params, {'q': ['Department'], 'sort': ['added_asc'], 'page': ['3']})
        header = parse_qs(urlsplit(response.context['column_headers'][0]['url']).query)
        self.assertEqual(header['q'], ['Department'])
        self.assertEqual(header['sort'], ['record_asc'])
        self.assertNotIn('page', header)
        self.assertNotContains(response, 'data-table-filter')
        self.assertContains(response, 'aria-current="page"')

    def test_existing_date_and_column_sorting(self):
        response = self.get(sort='record_desc')
        self.assertEqual(response.context['objects'][0].code, 'D044')
        self.assertEqual(self.get(sort='added_desc').context['objects'][0].pk, self.departments[-1].pk)
        self.assertEqual(self.get(sort='untrusted SQL').context['sort'], 'modified_desc')

    def test_all_resource_pages_render(self):
        for resource in RESOURCE_MODELS:
            with self.subTest(resource=resource):
                response = self.get(resource)
                self.assertEqual(response.status_code, 200)
                self.assertLessEqual(len(response.context['objects']), 20)

    def test_permissions(self):
        for role in (m.Role.FACULTY, m.Role.STUDENT):
            user = User.objects.create_user(username=role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertEqual(self.get(q='Department').status_code, 302)
        self.client.logout()
        self.assertEqual(self.get().status_code, 302)

    def test_role_admin_is_authorized(self):
        user = User.objects.create_user('role-admin')
        m.Profile.objects.create(user=user, role=m.Role.ADMIN)
        self.client.force_login(user)
        self.assertEqual(self.get().status_code, 200)

    def test_create_edit_delete_workflow(self):
        response = self.client.post(reverse('resource_create', args=['departments']), {'code': 'NEW', 'name': 'New department'})
        self.assertEqual(response.status_code, 302)
        obj = m.Department.objects.get(code='NEW')
        response = self.client.post(reverse('resource_update', args=['departments', obj.pk]), {'code': 'NEW', 'name': 'Edited department'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.get(q='Edited').context['objects'][0].pk, obj.pk)
        response = self.client.post(reverse('resource_delete', args=['departments', obj.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(m.Department.objects.filter(pk=obj.pk).exists())

    def test_many_to_many_search_deduplicates(self):
        course = m.Subject.objects.create(department=self.departments[0], code='COURSE', title='Course')
        required = m.Credential.objects.create(name='Main')
        requirement = m.SubjectCredentialRequirement.objects.create(subject=course, required_credential=required)
        requirement.acceptable_equivalents.add(m.Credential.objects.create(name='Equivalent One'), m.Credential.objects.create(name='Equivalent Two'))
        response = self.get('subject-credential-requirements', q='Equivalent')
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_database_limits_and_untruncated_results(self):
        for i in range(200):
            m.Department.objects.create(code=f'EX{i}', name='Extra')
        with CaptureQueriesContext(connection) as queries:
            response = self.get(q='Extra', page=2)
        self.assertEqual(response.context['page_obj'].paginator.count, 200)
        sql = [q['sql'] for q in queries if 'FROM "schedules_department"' in q['sql']]
        self.assertEqual(len(sql), 2)  # COUNT + bounded SELECT, not per-record queries.
        self.assertTrue(any('LIMIT 20 OFFSET 20' in q and 'LIKE' in q for q in sql))
        self.assertEqual(self.get(page=13).context['page_obj'].paginator.count, 245)


class RelatedListTests(SchedulingDefectFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser('related-admin', password='test')
        for i in range(24):
            course = m.Subject.objects.create(department=cls.department, code=f'COURSE{i:02}', title='Related Course', lecture_hours=2)
            parent = m.Assignment.objects.create(term=cls.term, subject=course, faculty=cls.faculty, section=cls.section)
            m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE', duration_minutes=0)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_assignment_query_count_and_page_bounded_prefetch(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse('resource_list', args=['assignments']))
        self.assertEqual(len(response.context['objects']), 20)
        self.assertLessEqual(len(captured), 8)
        meeting_queries = [q['sql'] for q in captured if 'FROM "schedules_teachingassignment"' in q['sql']]
        self.assertEqual(len(meeting_queries), 1)
        self.assertIn(' IN (', meeting_queries[0])
        self.assertContains(response, '120 min')
        with CaptureQueriesContext(connection) as before:
            old = m.Assignment.objects.select_related('subject', 'section__program', 'section__year_level', 'faculty', 'term').prefetch_related('meetings').order_by('-updated_at')[:200]
            durations = [meeting.required_duration_minutes for parent in old for meeting in parent.meetings.all()]
        self.assertTrue(durations)
        self.assertGreater(len(before), len(captured))
        print(f'Assignment list: previous data/render access {len(before)} queries for 25 rows; paginated HTTP render {len(captured)} queries for 20 rows.')

    def test_related_and_formatted_section_search(self):
        for value in (self.faculty.full_name, self.faculty.employee_id, str(self.section), self.term.school_year):
            with self.subTest(value=value):
                response = self.client.get(reverse('resource_list', args=['assignments']), {'q': value})
                self.assertEqual(response.context['page_obj'].paginator.count, 25)

    def test_schedule_tab_search_and_tie_order(self):
        for index in range(23):
            m.Schedule.objects.create(term=self.term, name='Draft Match')
        response = self.client.get(reverse('resource_list', args=['schedules']), {'tab': 'drafts', 'q': 'match', 'sort': 'record_asc'})
        self.assertEqual(response.context['page_obj'].paginator.count, 23)
        ids = [s.pk for s in response.context['objects']]
        self.assertEqual(ids, sorted(ids))
        params = parse_qs(urlsplit(response.context['pagination']['next']).query)
        self.assertEqual(params['tab'], ['drafts']); self.assertEqual(params['q'], ['match'])
        active = self.client.get(reverse('resource_list', args=['schedules']), {'q': 'match'})
        self.assertEqual(active.context['page_obj'].paginator.count, 0)

    def test_error_log_pages_do_not_change_filtered_summary_or_run_choices(self):
        runs = [m.GenerationRun.objects.create(term=self.term, requested_name=f'Run {i}', status='FAILED') for i in range(25)]
        for index in range(45):
            m.GenerationIssue.objects.create(run=runs[0], category='INVALID_DATA', severity='ERROR', short_description='Example issue', reason='Example', assignment=self.meetings[0])
        response = self.client.get(reverse('generation_error_log'), {'q': 'Example', 'severity': 'ERROR', 'page': 2, 'run_page': 2})
        self.assertEqual(len(response.context['issues']), 20)
        self.assertEqual(response.context['summary']['total'], 45)
        self.assertEqual(len(response.context['runs']), 5)
        self.assertEqual(len(response.context['run_choices']), 25)
        self.assertContains(response, 'value="ERROR" selected')
        params = parse_qs(urlsplit(response.context['issue_pagination']['next']).query)
        self.assertEqual(params['severity'], ['ERROR']); self.assertEqual(params['run_page'], ['2'])

    def test_generation_history_search(self):
        m.GenerationRun.objects.create(term=self.term, requested_name='Unique run', status='FAILED')
        response = self.client.get(reverse('generation_error_log'), {'run_q': 'unique'})
        self.assertEqual(len(response.context['runs']), 1)
        self.assertContains(response, 'value="unique"')
