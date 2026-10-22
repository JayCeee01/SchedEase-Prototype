"""Task 3.2: term history and draft relationship consistency."""
from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from . import models as m
from .test_known_defects import SchedulingDefectFixture


class TermProtectionTests(SchedulingDefectFixture):
    def setUp(self):
        self.other = m.AcademicTerm.objects.create(name='Other', school_year='2027', starts_on=date(2027, 1, 1), ends_on=date(2027, 6, 1))
        self.admin = User.objects.create_superuser(username='terms', password='test')
        self.client.force_login(self.admin)

    def schedule(self, status='PUBLISHED'):
        schedule = m.Schedule.objects.create(term=self.term, name='Protected')
        for i, meeting in enumerate(self.meetings):
            schedule.entries.create(assignment=meeting, room=self.room, day=0, start_time=time(8+i), end_time=time(9+i))
        m.ScheduleEntryAudit.objects.create(schedule=schedule, entry=schedule.entries.first(), user=self.admin,
                                           previous_values={'day': 1}, new_values={'day': 0})
        schedule.status = status
        schedule.save(update_fields=['status'])
        return schedule

    def test_published_and_archived_term_reassignment_rejected(self):
        for status in ('PUBLISHED', 'ARCHIVED'):
            with self.subTest(status=status):
                schedule = self.schedule(status)
                schedule.term = self.other
                with self.assertRaises(ValidationError):
                    schedule.save()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.Schedule.objects.filter(pk=schedule.pk).update(term=self.other)
                schedule.refresh_from_db()
                self.assertEqual(schedule.term_id, self.term.pk)
                self.assertEqual(schedule.entries.count(), 2)
                self.assertEqual(schedule.edit_audits.count(), 1)
                self.assertEqual(self.client.get(f'/schedules/{schedule.pk}/').status_code, 200)

    def test_protected_term_identifiers_and_dates_are_frozen(self):
        self.schedule()
        for field, value in [('name', 'Renamed'), ('school_year', '2099'), ('starts_on', date(2026, 7, 1)), ('ends_on', date(2026, 12, 31))]:
            with self.subTest(field=field):
                original = getattr(self.term, field)
                setattr(self.term, field, value)
                with self.assertRaisesMessage(ValidationError, 'published or archived'):
                    self.term.save()
                self.term.refresh_from_db()
                self.assertEqual(getattr(self.term, field), original)
        self.term.is_active = True
        self.term.save(update_fields=['is_active'])
        self.assertTrue(m.AcademicTerm.objects.get(pk=self.term.pk).is_active)

    def test_term_bulk_update_and_delete_are_atomic(self):
        self.schedule()
        old = self.other.name
        self.other.name = self.term.name = 'Changed'
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.AcademicTerm.objects.bulk_update([self.other, self.term], ['name'], batch_size=1)
        self.other.refresh_from_db()
        self.assertEqual(self.other.name, old)
        with self.assertRaises(ProtectedError), transaction.atomic():
            m.AcademicTerm.objects.filter(pk__in=[self.other.pk, self.term.pk]).delete()
        self.assertEqual(m.AcademicTerm.objects.count(), 2)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)

    def test_term_sql_deletion_update_and_replacement_are_rejected(self):
        self.schedule('ARCHIVED')
        statements = [
            ('UPDATE schedules_academicterm SET name=%s WHERE id=%s', ['Changed', self.term.pk]),
            ('DELETE FROM schedules_academicterm WHERE id=%s', [self.term.pk]),
            ('INSERT OR REPLACE INTO schedules_academicterm (id,name,school_year,starts_on,ends_on,is_active) VALUES (%s,%s,%s,%s,%s,0)',
             [self.term.pk, self.term.name, self.term.school_year, '2026-07-01', '2026-12-31']),
            ('INSERT OR REPLACE INTO schedules_academicterm (name,school_year,starts_on,ends_on,is_active) VALUES (%s,%s,%s,%s,0)',
             [self.term.name, self.term.school_year, '2026-07-01', '2026-12-31']),
        ]
        for sql, params in statements:
            with self.subTest(sql=sql):
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, params)
        self.term.refresh_from_db()
        self.assertEqual(self.term.starts_on, date(2026, 8, 1))

    def test_admin_and_resource_term_edits_are_rejected(self):
        self.schedule()
        data = {'name': 'Changed', 'school_year': self.term.school_year, 'starts_on': '2026-08-01', 'ends_on': '2026-12-01', '_save': 'Save'}
        for url in (f'/admin/schedules/academicterm/{self.term.pk}/change/', f'/schedules/manage/terms/{self.term.pk}/edit/'):
            with self.subTest(url=url):
                self.assertContains(self.client.post(url, data), 'published or archived')
        self.assertEqual(self.client.post(f'/admin/schedules/academicterm/{self.term.pk}/delete/', {'post': 'yes'}).status_code, 403)
        self.term.refresh_from_db()
        self.assertEqual(self.term.name, 'First Term')

    def test_related_finalized_records_cannot_move_terms(self):
        self.schedule('ARCHIVED')
        for obj in (self.parent, self.meetings[0]):
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(term=self.other)
                obj.refresh_from_db()
                self.assertEqual(obj.term_id, self.term.pk)

    def test_empty_draft_can_move_and_unrelated_term_remains_editable(self):
        draft = m.Schedule.objects.create(term=self.term, name='Empty')
        self.schedule()
        draft.term = self.other
        draft.save()
        self.other.name = 'Renamed'
        self.other.save()
        draft.refresh_from_db()
        self.assertEqual(draft.term_id, self.other.pk)
        self.assertEqual(draft.term.name, 'Renamed')

    def test_populated_draft_cannot_become_inconsistent(self):
        draft = self.schedule('DRAFT')
        draft.term = self.other
        with self.assertRaisesMessage(ValidationError, 'Academic terms must match'):
            draft.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Schedule.objects.filter(pk=draft.pk).update(term=self.other)
        response = self.client.post(f'/schedules/manage/schedules/{draft.pk}/edit/', {'term': self.other.pk, 'name': draft.name})
        self.assertContains(response, 'Academic terms must match')
        draft.refresh_from_db()
        self.assertEqual(draft.term_id, self.term.pk)

    def test_unscheduled_parent_term_save_synchronizes_children(self):
        self.parent.term = self.other
        self.parent.full_clean()
        self.parent.save()
        self.assertEqual(set(self.parent.meetings.values_list('term_id', flat=True)), {self.other.pk})

    def test_bulk_parent_term_change_cannot_leave_children_behind(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Assignment.objects.filter(pk=self.parent.pk).update(term=self.other)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.term_id, self.term.pk)

    def test_entry_and_meeting_terms_cannot_be_mixed(self):
        draft = m.Schedule.objects.create(term=self.other, name='Other draft')
        with self.assertRaises(ValidationError):
            draft.entries.create(assignment=self.meetings[0], room=self.room, day=0, start_time=time(8), end_time=time(9))
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ScheduleEntry.objects.bulk_create([m.ScheduleEntry(schedule=draft, assignment=self.meetings[0], room=self.room, day=0, start_time=time(8), end_time=time(9))])
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(term=self.other)
        self.assertFalse(draft.entries.exists())
