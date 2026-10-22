"""T2: backend conflict detection, boundaries and finalization contracts."""
from datetime import time

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from . import models as m
from .services.conflicts import schedule_validation_issues
from .services.ga import Gene
from .services.manual_edits import FIELDS, revision_token, save_manual_entry
from .services.publication import publish
from .test_known_defects import SchedulingDefectFixture


class ThesisConflictTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('t2-admin')
        self.schedule = m.Schedule.objects.create(term=self.term, name='T2')
        self.first = self.schedule.entries.create(assignment=self.meetings[0],
            room=self.room, day=0, start_time=time(8), end_time=time(9))
        self.second = self.schedule.entries.create(assignment=self.meetings[1],
            room=self.room, day=0, start_time=time(9), end_time=time(10))

    def test_partial_overlap_and_adjacency_agree_with_ga(self):
        ga = self.scheduler()
        for start, end, expected in [(time(7, 30), time(8, 30), 3),
                                     (time(8, 30), time(9, 30), 3),
                                     (time(7), time(8), 0),
                                     (time(9), time(10), 0)]:
            with self.subTest(start=start):
                self.schedule.entries.filter(pk=self.second.pk).update(start_time=start, end_time=end)
                categories = {i['issue'].category for i in schedule_validation_issues(self.schedule)}
                self.assertEqual(categories, {'FACULTY_CONFLICT', 'ROOM_CONFLICT', 'SECTION_CONFLICT'} if expected else set())
                genes = [Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9)),
                         Gene(self.meetings[1].pk, self.room.pk, 0, start, end)]
                self.assertEqual(ga.fitness(genes).hard_violations, expected)

    def test_manual_conflict_rejection_preserves_entry_revision_and_audit(self):
        baseline = self.schedule.updated_at
        proposed = {field: getattr(self.second, field) for field in FIELDS}
        proposed.update(start_time=time(8, 30), end_time=time(9, 30))
        with self.assertRaisesMessage(ValidationError, 'conflict'):
            save_manual_entry(schedule_id=self.schedule.pk, entry_id=self.second.pk,
                actor=self.admin, revision=revision_token(self.schedule, self.admin, self.second),
                proposed=proposed)
        self.second.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual(self.second.start_time, time(9))
        self.assertEqual(self.schedule.updated_at, baseline)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())

    def test_publication_rejects_persisted_conflicts_atomically(self):
        self.schedule.entries.filter(pk=self.second.pk).update(start_time=time(8, 30), end_time=time(9, 30))
        baseline = self.schedule.updated_at
        with self.assertRaisesMessage(ValidationError, 'Resolve conflicts'):
            publish(self.schedule, self.admin)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, m.ScheduleStatus.DRAFT)
        self.assertEqual(self.schedule.updated_at, baseline)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())
        self.assertFalse(m.ScheduleSnapshot.objects.exists())

    def test_adjacent_split_subject_meetings_can_publish(self):
        self.assertEqual(schedule_validation_issues(self.schedule), [])
        published, previous = publish(self.schedule, self.admin)
        self.assertEqual(published.status, m.ScheduleStatus.PUBLISHED)
        self.assertIsNone(previous)
        self.assertTrue(m.ScheduleSnapshot.objects.filter(schedule=published).exists())

    def test_duplicate_subject_meeting_and_schedule_entry_rejected(self):
        duplicate = m.TeachingAssignment(assignment=self.parent, term=self.term,
            subject=self.subject, faculty=self.faculty, section=self.section,
            component='LECTURE', meeting_index=1, duration_minutes=60)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        duplicate_entry = m.ScheduleEntry(schedule=self.schedule, assignment=self.meetings[0],
            room=self.room, day=1, start_time=time(8), end_time=time(9))
        with self.assertRaisesMessage(ValidationError, 'already exists'):
            duplicate_entry.full_clean()

    def test_same_subject_parallel_sections_are_valid(self):
        section = m.Section.objects.create(program=self.section.program,
            year_level=self.section.year_level, name='B', size=20)
        faculty = m.Faculty.objects.create(department=self.department, employee_id='T2-B', full_name='Other')
        room = m.Room.objects.create(name='Other room', capacity=30, room_type='LECTURE')
        parent = m.Assignment.objects.create(term=self.term, subject=self.subject, section=section, faculty=faculty)
        for index in (1, 2):
            meeting = m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE',
                meeting_index=index, duration_minutes=60)
            entry = m.ScheduleEntry(schedule=self.schedule, assignment=meeting, room=room,
                day=0, start_time=time(7 + index), end_time=time(8 + index))
            entry.full_clean()
            entry.save()
        self.assertEqual(schedule_validation_issues(self.schedule), [])
