"""Task 6.2: counts, allowlisted ordering, validated filters and URL state."""
from datetime import date, time
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from .services.listing import EXTRA_SORTS, FILTERS
from .test_known_defects import SchedulingDefectFixture


class RecordControlTests(SchedulingDefectFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser('control-admin', password='test')
        cls.other_department = m.Department.objects.create(code='OTHER', name='Other')
        cls.other_term = m.AcademicTerm.objects.create(name='Second Term', school_year='2026-2027',
            starts_on=date(2027, 1, 1), ends_on=date(2027, 5, 1))
        cls.credential = m.Credential.objects.create(name='License')
        m.FacultyCredential.objects.create(faculty=cls.faculty, credential=cls.credential)
        m.SubjectCredentialRequirement.objects.create(subject=cls.subject, required_credential=cls.credential)
        m.Student.objects.create(full_name='Student', student_number='S1', section=cls.section)
        m.Availability.objects.create(room=cls.room, day=0, start_time=time(8), end_time=time(17))
        for i in range(24):
            subject = m.Subject.objects.create(code=f'C{i:02}', title='Shared name', department=cls.department)
            m.Assignment.objects.create(subject=subject, term=cls.term, section=cls.section, faculty=cls.faculty)
        m.Subject.objects.create(code='OTHER', title='Other course', department=cls.other_department)
        m.Room.objects.create(name='Large lab', room_type=m.RoomKind.COMPUTER_LAB, capacity=60, is_active=False)

    def setUp(self):
        self.client.force_login(self.admin)

    def get(self, resource='assignments', **params):
        return self.client.get(reverse('resource_list', args=[resource]), params)

    def test_counts_and_ranges_across_pages(self):
        for page, start, end in [(1, 1, 20), (2, 21, 24)]:
            response = self.get('subjects', q='Shared', page=page)
            self.assertEqual(response.context['total_count'], 26)
            self.assertEqual(response.context['filtered_count'], 24)
            self.assertContains(response, f'Showing {start}–{end}')
            self.assertContains(response, '26 total')
            self.assertContains(response, '24 matching')

    def test_empty_and_zero_matches(self):
        for resource, params, total in [('ga-settings', {}, 0), ('subjects', {'q': 'absent'}, 26)]:
            response = self.get(resource, **params)
            self.assertEqual(response.context['total_count'], total)
            self.assertEqual(response.context['filtered_count'], 0)
            self.assertContains(response, 'Showing 0–0')

    def test_no_count_or_choices_leaked_to_other_roles(self):
        for role in (m.Role.STUDENT, m.Role.FACULTY):
            user = User.objects.create_user(role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            with CaptureQueriesContext(connection) as queries:
                response = self.get(term=self.term.pk)
            self.assertEqual(response.status_code, 302)
            self.assertNotIn(b'25 total', response.content)
            self.assertFalse(any('schedules_assignment' in row['sql'] or 'schedules_academicterm' in row['sql'] for row in queries))
        self.client.logout()
        self.assertEqual(self.get().status_code, 302)

    def test_role_admin_can_use_filters(self):
        user = User.objects.create_user('authorized')
        m.Profile.objects.create(user=user, role=m.Role.ADMIN)
        self.client.force_login(user)
        self.assertEqual(self.get(term=self.term.pk).context['filtered_count'], 25)

    def test_term_filter_and_tab_count_scopes(self):
        m.Schedule.objects.create(name='First', term=self.term)
        m.Schedule.objects.create(name='Second', term=self.other_term)
        response = self.get('schedules', tab='drafts', term=self.term.pk)
        self.assertEqual((response.context['total_count'], response.context['filtered_count']), (2, 1))
        self.assertEqual(response.context['objects'][0].term_id, self.term.pk)
        # Published tab does not count drafts, even with the same term selected.
        response = self.get('schedules', tab='active', term=self.term.pk)
        self.assertEqual((response.context['total_count'], response.context['filtered_count']), (0, 0))
        self.assertEqual(self.get(term=self.other_term.pk).context['filtered_count'], 0)

    def test_capacity_sort_directions(self):
        self.assertEqual([room.capacity for room in self.get('rooms', sort='capacity_asc').context['objects']], [30, 60])
        self.assertEqual([room.capacity for room in self.get('rooms', sort='capacity_desc').context['objects']], [60, 30])

    def test_related_sort(self):
        first = self.get('subjects', sort='department_asc').context['objects'][0]
        self.assertEqual(first.department_id, self.other_department.pk)
        first = self.get('subjects', sort='department_desc').context['objects'][0]
        self.assertEqual(first.department_id, self.department.pk)

    def test_equal_values_have_stable_unique_order_across_pages(self):
        expected = list(m.Subject.objects.filter(title='Shared name').order_by('pk').values_list('pk', flat=True))
        for direction, ids in [('asc', expected), ('desc', expected[::-1])]:
            actual = []
            for page in (1, 2):
                actual.extend(obj.pk for obj in self.get('subjects', q='Shared', sort=f'title_{direction}', page=page).context['objects'])
            self.assertEqual(actual, ids)

    def test_invalid_sort_uses_safe_default_and_canonical_links(self):
        for value in ('department__name', '-pk', 'name; DROP TABLE schedules_subject', '<script>'):
            response = self.get('subjects', sort=value)
            self.assertEqual(response.context['sort'], 'modified_desc')
            params = parse_qs(urlsplit(response.context['pagination']['next']).query)
            self.assertEqual(params['sort'], ['modified_desc'])
        self.assertEqual(m.Subject.objects.count(), 26)

    def test_all_extra_sort_options_resolve(self):
        for resource, fields in EXTRA_SORTS.items():
            for key, _, _ in fields:
                for direction in ('asc', 'desc'):
                    with self.subTest(resource=resource, sort=key, direction=direction):
                        response = self.get(resource, sort=f'{key}_{direction}')
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context['sort'], f'{key}_{direction}')

    def test_multiple_filters_search_and_sort(self):
        response = self.get(q='C0', term=self.term.pk, department=self.department.pk,
            program=self.section.program_id, year=self.section.year_level_id, sort='course_desc')
        self.assertEqual(response.context['filtered_count'], 10)
        self.assertEqual(response.context['objects'][0].subject.code, 'C09')
        self.assertEqual(response.context['total_count'], 25)
        self.assertContains(response, 'Filters applied')

    def test_room_choices_and_boolean_filters(self):
        response = self.get('rooms', room_type='COMPUTER_LAB', active='0')
        self.assertEqual([obj.name for obj in response.context['objects']], ['Large lab'])
        self.assertEqual(self.get('rooms', room_type='COMPUTER_LAB', active='1').context['filtered_count'], 0)
        self.assertEqual(self.get('rooms', active='1').context['filtered_count'], 1)

    def test_all_filter_controls_accept_model_supported_values(self):
        values = {'department': self.department.pk, 'program': self.section.program_id,
            'year': self.section.year_level_id, 'term': self.term.pk, 'credential': self.credential.pk,
            'room_type': 'LECTURE', 'active': '1', 'status': 'DRAFT', 'day': '0', 'kind': 'AVAILABLE'}
        for resource, definitions in FILTERS.items():
            for key, _ in definitions:
                with self.subTest(resource=resource, filter=key):
                    response = self.get(resource, **{key: values[key]})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['filter_errors'], [])

    def test_invalid_and_stale_filters_fail_closed_without_errors(self):
        stale = m.Department.objects.create(code='STALE', name='Deleted')
        stale_id = stale.pk
        stale.delete()
        for value in ('abc', '-1', '9' * 500, str(stale_id), '1 OR 1=1', '<script>'):
            response = self.get('subjects', department=value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['filtered_count'], 0)
            self.assertEqual(response.context['total_count'], 26)
            self.assertContains(response, 'Choose another option or select All.')
            self.assertContains(response, 'aria-invalid="true"')
        for key, value in [('active', 'true'), ('room_type', 'FAKE')]:
            self.assertEqual(self.get('rooms', **{key: value}).context['filtered_count'], 0)

    def test_related_search_and_filters_do_not_duplicate_counts_or_rows(self):
        requirement = m.SubjectCredentialRequirement.objects.get(subject=self.subject)
        requirement.acceptable_equivalents.add(m.Credential.objects.create(name='Alternate one'), m.Credential.objects.create(name='Alternate two'))
        response = self.get('subject-credential-requirements', q='Alternate', credential=self.credential.pk)
        self.assertEqual((response.context['total_count'], response.context['filtered_count']), (1, 1))
        self.assertEqual([obj.pk for obj in response.context['objects']], [requirement.pk])

    def test_state_persists_in_links_and_controls_and_resets_page(self):
        response = self.get(q='C', term=self.term.pk, program=self.section.program_id, sort='course_desc', page=1)
        params = parse_qs(urlsplit(response.context['pagination']['next']).query)
        self.assertEqual(params, {'q': ['C'], 'term': [str(self.term.pk)], 'program': [str(self.section.program_id)], 'sort': ['course_desc'], 'page': ['2']})
        header = parse_qs(urlsplit(response.context['column_headers'][0]['url']).query)
        self.assertNotIn('page', header)
        self.assertEqual(header['term'], [str(self.term.pk)])
        self.assertContains(response, f'value="{self.term.pk}" selected')
        self.assertNotContains(response, 'name="page"')
        cleared = parse_qs(urlsplit(response.context['clear_url']).query)
        self.assertEqual(cleared, {'sort': ['course_desc']})

    def test_schedule_tab_links_retain_term_and_reset_conflicting_status(self):
        response = self.get('schedules', tab='drafts', status='DRAFT', term=self.term.pk, q='x', page=4)
        params = parse_qs(urlsplit(response.context['tab_links']['archived']).query)
        self.assertEqual(params, {'tab': ['archived'], 'term': [str(self.term.pk)], 'q': ['x']})

    def test_duplicate_and_unknown_url_parameters_are_not_propagated(self):
        response = self.client.get(reverse('resource_list', args=['assignments']) +
            f'?sort=bad&sort=course_asc&term=invalid&term={self.term.pk}&unsafe=x&page=1')
        params = parse_qs(urlsplit(response.context['pagination']['next']).query)
        self.assertEqual(params, {'sort': ['course_asc'], 'term': [str(self.term.pk)], 'page': ['2']})

    def test_counts_and_filters_keep_queries_bounded(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.get(term=self.term.pk, department=self.department.pk, q='C', page=2)
        self.assertEqual(response.context['filtered_count'], 25)  # Includes Regression Course.
        self.assertLessEqual(len(queries), 8)
        self.assertEqual(sum('COUNT(' in row['sql'] for row in queries), 1)
        self.assertTrue(any('LIMIT 5 OFFSET 20' in row['sql'] for row in queries))
        print(f'Task 6.2 filtered assignment HTTP render: {len(queries)} queries, one combined count.')
