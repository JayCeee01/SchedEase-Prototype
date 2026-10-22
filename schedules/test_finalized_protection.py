"""H2: finalized content is protected even when model validation is bypassed."""
from datetime import time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from . import models as m
from .test_known_defects import SchedulingDefectFixture


class FinalizedProtectionTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="h2", password="test")
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name="Official")
        self.entries = [self.schedule.entries.create(assignment=meeting, room=self.room, day=0,
                        start_time=time(8+i), end_time=time(9+i)) for i, meeting in enumerate(self.meetings)]
        self.audit = m.ScheduleEntryAudit.objects.create(schedule=self.schedule, entry=self.entries[0],
                        user=self.admin, previous_values={"day": 1}, new_values={"day": 0})
        self.schedule.status = m.ScheduleStatus.PUBLISHED
        self.schedule.save(update_fields=["status"])

    def test_related_content_saves_are_rejected(self):
        records = [(self.subject, 'title', 'Changed'), (self.faculty, 'full_name', 'Changed'),
                   (self.room, 'capacity', 999), (self.section, 'name', 'CHANGED'),
                   (self.section.program, 'code', 'CHANGED'), (self.section.year_level, 'label', 'Changed'),
                   (self.department, 'name', 'Changed'), (self.meetings[0], 'duration_minutes', 30)]
        for obj, field, value in records:
            with self.subTest(model=type(obj).__name__):
                original = getattr(obj, field)
                setattr(obj, field, value)
                with self.assertRaisesMessage(ValidationError, 'published or archived'):
                    obj.save()
                obj.refresh_from_db()
                self.assertEqual(getattr(obj, field), original)

    def test_assignment_reassignment_is_rejected(self):
        faculty = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Other')
        self.parent.faculty = faculty
        with self.assertRaises(ValidationError):
            self.parent.save()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.faculty_id, self.faculty.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Assignment.objects.filter(pk=self.parent.pk).update(faculty=faculty)

    def test_entries_cannot_be_updated_moved_added_or_deleted(self):
        entry = self.entries[0]
        draft = m.Schedule.objects.create(term=self.term, name='Draft')
        for changes in ({'day': 1}, {'start_time': time(7)}, {'room_id': self.room.pk + 100},
                        {'faculty_override_id': self.faculty.pk}, {'schedule_id': draft.pk}):
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.ScheduleEntry.objects.filter(pk=entry.pk).update(**changes)
        with self.assertRaises(ValidationError):
            self.schedule.entries.create(assignment=self.meetings[0], room=self.room, day=2,
                                         start_time=time(8), end_time=time(9))
        with self.assertRaises(ProtectedError), transaction.atomic():
            entry.delete()
        self.assertEqual(self.schedule.entries.count(), 2)
        self.assertTrue(m.ScheduleEntryAudit.objects.filter(pk=self.audit.pk).exists())

    def test_bulk_create_and_move_into_finalized_schedule_are_rejected(self):
        draft = m.Schedule.objects.create(term=self.term, name='Draft')
        entry = draft.entries.create(assignment=self.meetings[0], room=self.room, day=2,
                                     start_time=time(8), end_time=time(9))
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ScheduleEntry.objects.filter(pk=entry.pk).update(schedule=self.schedule)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ScheduleEntry.objects.bulk_create([m.ScheduleEntry(schedule=self.schedule, assignment=self.meetings[0],
                         room=self.room, day=3, start_time=time(8), end_time=time(9))])
        entry.refresh_from_db()
        self.assertEqual(entry.schedule_id, draft.pk)

    def test_mixed_bulk_update_is_atomic(self):
        free = m.Room.objects.create(name='Free', capacity=25, room_type='LECTURE')
        for operation in ('update', 'bulk_update'):
            with self.subTest(operation=operation):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    if operation == 'update':
                        m.Room.objects.filter(pk__in=[free.pk, self.room.pk]).update(capacity=99)
                    else:
                        free.capacity = self.room.capacity = 99
                        m.Room.objects.bulk_update([free, self.room], ['capacity'], batch_size=1)
                free.refresh_from_db()
                self.room.refresh_from_db()
                self.assertEqual(free.capacity, 25)
                self.assertEqual(self.room.capacity, 30)

    def test_bulk_and_cascade_deletions_preserve_history(self):
        for obj in (self.schedule, self.parent, self.meetings[0], self.term, self.audit):
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).delete()
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
        self.assertEqual(self.schedule.entries.count(), 2)
        self.assertTrue(m.ScheduleEntryAudit.objects.filter(pk=self.audit.pk).exists())

    def test_raw_sql_and_replacement_cannot_bypass_guards(self):
        for sql, values in [
            ('UPDATE schedules_subject SET title=%s WHERE id=%s', ['Changed', self.subject.pk]),
            ('DELETE FROM schedules_scheduleentry WHERE id=%s', [self.entries[0].pk]),
            ('UPDATE schedules_schedule SET status=%s WHERE id=%s', ['DRAFT', self.schedule.pk]),
            ('INSERT OR REPLACE INTO schedules_room (id,name,room_type,capacity,is_active) VALUES (%s,%s,%s,999,1)',
             [self.room.pk, self.room.name, self.room.room_type]),
        ]:
            with self.subTest(sql=sql):
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, values)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 30)

    def test_admin_edit_and_delete_are_blocked(self):
        response = self.client.post(f'/admin/schedules/room/{self.room.pk}/change/', {
            'name': 'Changed', 'capacity': 30, 'room_type': 'LECTURE', 'is_active': 'on', '_save': 'Save'})
        self.assertContains(response, 'published or archived')
        self.assertEqual(self.client.post(f'/admin/schedules/room/{self.room.pk}/delete/', {'post': 'yes'}).status_code, 403)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, 'Regression Room')

    def test_manual_and_resource_views_reject_changes(self):
        entry = self.entries[0]
        response = self.client.post(f'/schedules/{self.schedule.pk}/entry/{entry.pk}/edit/', {
            'assignment': entry.assignment_id, 'room': self.room.pk, 'day': 1,
            'start_time': '08:00', 'end_time': '09:00'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(f'/schedules/manage/rooms/{self.room.pk}/edit/', {
            'name': 'Changed', 'capacity': 30, 'room_type': 'LECTURE', 'is_active': 'on'})
        self.assertContains(response, 'published or archived')
        entry.refresh_from_db()
        self.assertEqual(entry.day, 0)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)

    def test_draft_only_records_remain_editable(self):
        room = m.Room.objects.create(name='Draft room', capacity=30, room_type='LECTURE')
        draft = m.Schedule.objects.create(term=self.term, name='Draft')
        entry = draft.entries.create(assignment=self.meetings[0], room=room, day=0, start_time=time(8), end_time=time(9))
        m.Room.objects.filter(pk=room.pk).update(name='Renamed')
        entry.day = 1
        entry.save()
        entry.delete()
        draft.delete()
        room.refresh_from_db()
        self.assertEqual(room.name, 'Renamed')
        self.assertEqual(self.schedule.entries.count(), 2)

    def test_archived_records_stay_locked_and_readable(self):
        from .protection import archive_transition
        self.schedule.status = m.ScheduleStatus.ARCHIVED
        with archive_transition():
            self.schedule.save(update_fields=['status'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(component='LABORATORY')
        with self.assertRaises(ValidationError):
            self.schedule.status = m.ScheduleStatus.PUBLISHED
            self.schedule.save(update_fields=['status'])
        self.assertEqual(self.client.get(f'/schedules/{self.schedule.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/schedules/{self.schedule.pk}/export/csv/').status_code, 200)

    def test_ordinary_archiving_and_audit_rewrite_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Schedule.objects.filter(pk=self.schedule.pk).update(status='ARCHIVED')
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ScheduleEntryAudit.objects.filter(pk=self.audit.pk).update(previous_values={})
        self.audit.refresh_from_db()
        self.assertEqual(self.audit.previous_values, {'day': 1})

    def test_cannot_attach_new_meeting_to_protected_parent(self):
        with self.assertRaises(ValidationError):
            self.parent.meetings.create(component='LECTURE', meeting_index=3, duration_minutes=60)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.TeachingAssignment.objects.bulk_create([m.TeachingAssignment(assignment=self.parent,
                term=self.term, subject=self.subject, faculty=self.faculty, section=self.section,
                component='LECTURE', meeting_index=3, duration_minutes=60)])
        self.assertEqual(self.parent.meetings.count(), 2)

    def test_admin_bulk_delete_keeps_protected_and_unrelated_records(self):
        free = m.Room.objects.create(name='Free', capacity=25, room_type='LECTURE')
        response = self.client.post('/admin/schedules/room/', {
            'action': 'delete_selected', '_selected_action': [self.room.pk, free.pk], 'post': 'yes'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['protected'])
        self.assertEqual(m.Room.objects.filter(pk__in=[self.room.pk, free.pk]).count(), 2)

    def test_effective_override_records_are_protected(self):
        other = m.Faculty.objects.create(department=self.department, employee_id='OVERRIDE', full_name='Override')
        draft = m.Schedule.objects.create(term=self.term, name='Override history')
        draft.entries.create(assignment=self.meetings[0], faculty_override=other, room=self.room,
                             day=0, start_time=time(8), end_time=time(9))
        draft.status = m.ScheduleStatus.ARCHIVED
        draft.save(update_fields=['status'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Faculty.objects.filter(pk=other.pk).update(full_name='Changed')
        other.refresh_from_db()
        self.assertEqual(other.full_name, 'Override')

    def test_archiving_scope_does_not_unlock_content(self):
        from .protection import archive_transition
        with archive_transition():
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Schedule.objects.filter(pk=self.schedule.pk).update(status='ARCHIVED', name='Changed')
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, m.ScheduleStatus.PUBLISHED)
        self.assertEqual(self.schedule.name, 'Official')
