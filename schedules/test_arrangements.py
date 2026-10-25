from datetime import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse

from . import models as m
from .services.arrangements import suggested_arrangements
from .test_known_defects import SchedulingDefectFixture


class ArrangementSuggestionTests(SimpleTestCase):
    def test_valid_bounded_exact_splits(self):
        self.assertEqual(suggested_arrangements(3), [[180], [90, 90], [60, 60, 60]])
        self.assertEqual(suggested_arrangements(2), [[120], [60, 60], [30, 30, 30, 30]])
        self.assertEqual(suggested_arrangements(0), [])
        for hours in range(1, 65):
            for values in suggested_arrangements(hours):
                self.assertLessEqual(len(values), 4)
                self.assertEqual(sum(values), hours * 60)
                self.assertTrue(all(0 < value <= 720 and value % 30 == 0 for value in values))


class ArrangementEditorTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('arrangement-admin')
        self.client.force_login(self.admin)
        self.url = reverse('resource_update', args=['assignments', self.parent.pk])

    def payload(self):
        data = dict(subject=self.subject.pk, faculty=self.faculty.pk, section=self.section.pk, term=self.term.pk)
        data.update({'meetings-TOTAL_FORMS': '2', 'meetings-INITIAL_FORMS': '2',
                     'meetings-MIN_NUM_FORMS': '1', 'meetings-MAX_NUM_FORMS': '1000'})
        for i, meeting in enumerate(self.meetings):
            for key in ('id', 'meeting_index', 'component', 'duration_minutes', 'required_room_type_override'):
                data[f'meetings-{i}-{key}'] = getattr(meeting, key)
        return data

    def schedule(self):
        schedule = m.Schedule.objects.create(term=self.term, name='Referenced')
        for i, meeting in enumerate(self.meetings):
            schedule.entries.create(assignment=meeting, room=self.room, day=0,
                                    start_time=time(8+i), end_time=time(9+i))
        return schedule

    def test_custom_unequal_durations_keep_identity_and_room_settings(self):
        data = self.payload()
        data.update({'meetings-0-duration_minutes': 45, 'meetings-1-duration_minutes': 75,
                     'meetings-0-required_room_type_override': 'SPECIAL'})
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.meetings[0].refresh_from_db()
        self.assertEqual(self.meetings[0].duration_minutes, 45)
        self.assertEqual(self.meetings[0].required_room_type_override, 'SPECIAL')
        self.assertEqual(set(self.parent.meetings.values_list('pk', flat=True)), {m.pk for m in self.meetings})

    def test_nonexact_total_is_rejected(self):
        data = self.payload(); data['meetings-0-duration_minutes'] = 90
        response = self.client.post(self.url, data)
        self.assertContains(response, 'course requires 120')
        self.meetings[0].refresh_from_db()
        self.assertEqual(self.meetings[0].duration_minutes, 60)

    def test_draft_restores_arrangement_as_custom_without_saving(self):
        data = self.payload(); data.update({'meetings-0-duration_minutes': 45, 'meetings-1-duration_minutes': 75})
        self.client.post(reverse('save_form_draft'), {'resource': 'assignments', 'object_pk': str(self.parent.pk),
                         'changed': True, 'payload': data}, content_type='application/json')
        response = self.client.get(self.url)
        self.assertEqual(response.context['meetings'].forms[0]['duration_minutes'].value(), '45')
        self.assertContains(response, 'data-arrangement-controls')
        self.meetings[0].refresh_from_db()
        self.assertEqual(self.meetings[0].duration_minutes, 60)

    def test_scheduled_and_finalized_assignments_reject_changes(self):
        schedule = self.schedule()
        from .services.publication import publish
        for finalize in (False, True):
            if finalize:
                publish(schedule, self.admin)
            self.assertNotContains(self.client.get(self.url), 'data-arrangement-controls')
            data = self.payload(); data.update({'meetings-0-duration_minutes': 45, 'meetings-1-duration_minutes': 75})
            response = self.client.post(self.url, data)
            self.assertContains(response, 'published or archived schedule' if finalize else 'Meeting arrangements cannot change')
            self.meetings[0].refresh_from_db()
            self.assertEqual(self.meetings[0].duration_minutes, 60)

    def test_reference_added_before_save_is_rechecked(self):
        from .forms import AssignmentMeetingFormSet
        original = AssignmentMeetingFormSet.check_scheduled_arrangement
        calls = []
        def check(formset):
            calls.append(True)
            if len(calls) == 2:
                self.schedule()
            return original(formset)
        data = self.payload(); data.update({'meetings-0-duration_minutes': 45, 'meetings-1-duration_minutes': 75})
        with patch.object(AssignmentMeetingFormSet, 'check_scheduled_arrangement', check):
            response = self.client.post(self.url, data)
            self.assertContains(response, 'Meeting arrangements cannot change')
        self.meetings[0].refresh_from_db()
        self.assertEqual(self.meetings[0].duration_minutes, 60)

    def test_roles_cannot_edit(self):
        for role in (m.Role.STUDENT, m.Role.FACULTY):
            user = User.objects.create_user('arrangement-' + role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
            self.assertEqual(self.client.get(self.url).status_code, 302)
