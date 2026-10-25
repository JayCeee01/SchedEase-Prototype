from datetime import time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.room_compatibility import meeting_room_errors
from .services.placements import feasible_placements
from .services.publication import publish


class RoomCompatibilityTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('room-policy-admin')
        self.client.force_login(self.admin)

    def test_component_matrix_and_explicit_configuration(self):
        meeting = self.meetings[0]
        for component in ('LECTURE', 'LABORATORY'):
            meeting.component = component
            for kind in m.RoomKind.values:
                for override in ('', kind):
                    self.subject.required_room_type = kind
                    meeting.subject = self.subject
                    meeting.required_room_type_override = override
                    expected = kind == 'LECTURE' if component == 'LECTURE' else kind != 'LECTURE'
                    self.assertEqual(not meeting_room_errors(meeting), expected, (component, kind, override))
        self.subject.required_room_type = 'LECTURE'
        meeting.required_room_type_override = 'COMPUTER_LAB'
        self.assertEqual(meeting_room_errors(meeting), [])
        meeting.required_room_type_override = 'LECTURE'
        self.assertIn('Laboratory cannot use Lecture Room', meeting_room_errors(meeting)[0])

    def test_incompatible_draft_blocks_manual_ga_and_publication(self):
        m.Subject.objects.filter(pk=self.subject.pk).update(required_room_type='COMPUTER_LAB')
        m.Room.objects.filter(pk=self.room.pk).update(room_type='COMPUTER_LAB')
        meeting = m.TeachingAssignment.objects.get(pk=self.meetings[0].pk)
        room = m.Room.objects.get(pk=self.room.pk)
        with self.assertRaisesMessage(ValidationError, 'Lecture requires Lecture Room'):
            meeting.full_clean()
        options, errors = feasible_placements(meeting, self.term, [room])
        self.assertFalse(options)
        self.assertTrue(any('Lecture requires Lecture Room' in e for e in errors))
        self.assertTrue(any('Lecture requires Lecture Room' in e for e in self.scheduler().preflight_issues()))
        schedule = m.Schedule.objects.create(term=self.term, name='Invalid draft')
        entry = m.ScheduleEntry(schedule=schedule, assignment=meeting, room=room, day=0, start_time=time(8), end_time=time(9))
        with self.assertRaisesMessage(ValidationError, 'Lecture requires Lecture Room'):
            entry.full_clean()
        # Legacy stored data can exist; publication must still reject it.
        entry.save()
        url = f'/schedules/{schedule.pk}/entry/{entry.pk}/edit/'
        revision = self.client.get(url).context['form'].initial['revision']
        response = self.client.post(url, {'revision': revision, 'assignment': meeting.pk,
            'room': room.pk, 'day': 1, 'start_time': '08:00', 'end_time': '09:00'})
        self.assertContains(response, 'Lecture requires Lecture Room')
        entry.refresh_from_db()
        self.assertEqual(entry.day, 0)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())
        from .services.corrections import placement_suggestions
        self.assertEqual(placement_suggestions(entry, self.admin), [])
        with self.assertRaises(ValidationError):
            publish(schedule, self.admin)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'DRAFT')

    def test_smart_repair_rejects_incompatible_legacy_meetings_without_changes(self):
        from .services import smart_repair
        source = m.Schedule.objects.create(term=self.term, name='Repair source')
        for i, meeting in enumerate(self.meetings):
            source.entries.create(assignment=meeting, room=self.room, day=0,
                                  start_time=time(8+i), end_time=time(9+i))
        source.status = 'PUBLISHED'
        source.save(update_fields=['status'])
        draft = smart_repair.create_draft(source.pk, self.admin, dict(
            kind='room', resource=self.room.pk, day=0, start='08:00', end='09:00', rearrange=False))
        before = list(draft.entries.values())
        # Simulate legacy incompatibility in the service's loaded objects only;
        # finalized database records and their protection triggers stay intact.
        from unittest.mock import patch
        with patch('schedules.services.room_compatibility.meeting_room_errors',
                   return_value=['Legacy meeting: Lecture requires Lecture Room.']):
            result = smart_repair.propose(draft.pk, self.admin)
        self.assertFalse(result['success'])
        self.assertIsNone(result['token'])
        self.assertIn('Legacy meeting: Lecture requires Lecture Room.', result['reasons'])
        self.assertEqual(list(draft.entries.values()), before)
        self.assertEqual(source.status, 'PUBLISHED')

    def test_inline_creation_rejects_lab_inheriting_lecture_default(self):
        m.Subject.objects.filter(pk=self.subject.pk).update(lecture_hours=0, lab_hours=2)
        self.parent.delete()
        data = {'subject': self.subject.pk, 'faculty': self.faculty.pk, 'section': self.section.pk, 'term': self.term.pk,
                'meetings-TOTAL_FORMS': '1', 'meetings-INITIAL_FORMS': '0', 'meetings-MIN_NUM_FORMS': '1',
                'meetings-MAX_NUM_FORMS': '1000', 'meetings-0-component': 'LABORATORY',
                'meetings-0-duration_minutes': '120', 'meetings-0-meeting_index': '1'}
        url = reverse('resource_create', args=['assignments'])
        self.assertContains(self.client.post(url, data), 'Laboratory cannot use Lecture Room')
        self.assertFalse(m.Assignment.objects.exists())
        data['meetings-0-required_room_type_override'] = 'COMPUTER_LAB'
        self.assertEqual(self.client.post(url, data).status_code, 302)

    def test_explicit_lecture_override_of_lab_course_is_valid(self):
        self.subject.required_room_type = 'SCIENCE_LAB'
        self.subject.save()
        meeting = m.TeachingAssignment.objects.get(pk=self.meetings[0].pk)
        meeting.required_room_type_override = 'LECTURE'
        meeting.full_clean()
        options, errors = feasible_placements(meeting, self.term, [self.room])
        self.assertTrue(options)
        self.assertFalse(errors)

    def test_workbook_incompatible_room_is_rejected_atomically(self):
        from unittest.mock import patch
        from django.core.management.base import CommandError
        from django.db import transaction
        from .management.commands import import_tertiary_full as module
        data = dict(program='BSCS', year=1, section='A', faculty='Example', duration=60,
                    room='Lecture room', room_type='LECTURE', units='3', code='NEW101', title='Example',
                    component='LABORATORY', source_key='synthetic', sheet='Example', row=2,
                    day=0, start=time(9), end=time(10))
        before = m.TeachingAssignment.objects.count()
        with self.assertRaisesMessage(CommandError, 'Laboratory cannot use Lecture Room'):
            with transaction.atomic(), patch.dict(module.PROGRAMS,
                    {'BSCS': ('NEW', 'New department', 'Program')}, clear=True):
                module.Command().persist([data])
        self.assertEqual(m.TeachingAssignment.objects.count(), before)
        self.assertFalse(m.Subject.objects.filter(code='NEW101').exists())
