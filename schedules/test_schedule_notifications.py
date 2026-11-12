from django.db import transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from . import models as m
from . import test_student_timetable as fixtures
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish
from .services.schedule_notifications import record_publication, visible_notifications


class NotificationTests(SchedulingDefectFixture):
    setUp = fixtures.StudentTimetableTests.setUp

    def test_published_recipients_idempotency_and_read(self):
        self.assertEqual(m.ScheduleNotification.objects.count(), 0)
        locked, _ = publish(self.schedule, self.admin)
        notice = m.ScheduleNotification.objects.get(user=self.user)
        self.assertEqual(notice.kind, 'NEW')
        record_publication(locked, None, {})
        self.assertEqual(m.ScheduleNotification.objects.count(), 1)
        self.client.force_login(self.user)
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, '1 unread')
        self.assertNotContains(page, 'data-sort')
        self.assertNotContains(page, 'continuous-grid')
        self.assertEqual(self.client.get(reverse('notification_read', args=[notice.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('notification_read', args=[notice.pk])).status_code, 302)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('notification_read', args=[notice.pk])).status_code, 404)

    def test_failed_publish_and_outer_rollback(self):
        with self.assertRaises(ValidationError):
            publish(self.schedule, self.user)
        self.assertFalse(m.ScheduleNotification.objects.exists())
        self.schedule.refresh_from_db()
        with transaction.atomic():
            publish(self.schedule, self.admin)
            self.assertEqual(m.ScheduleNotification.objects.count(), 1)
            transaction.set_rollback(True)
        self.assertFalse(m.ScheduleNotification.objects.exists())

    def test_replacement_and_changed_scope(self):
        publish(self.schedule, self.admin)
        replacement = m.Schedule.objects.create(term=self.term, name='Replacement')
        for entry in self.entries:
            replacement.entries.create(assignment=entry.assignment, room=entry.room, day=entry.day,
                start_time=entry.start_time, end_time=entry.end_time)
        publish(replacement, self.admin, replace_confirmed=True)
        notice = m.ScheduleNotification.objects.get(schedule=replacement, user=self.user)
        self.assertEqual(notice.kind, 'UPDATED')
        self.assertEqual([n.pk for n in visible_notifications(self.user)], [notice.pk])
        student = self.user.student
        student.user = None
        student.save()
        self.assertEqual(visible_notifications(self.user), [])

    def test_faculty_withdrawal_and_unrelated_users(self):
        from django.contrib.auth.models import User
        faculty_user = User.objects.create_user('notified-faculty')
        m.Profile.objects.create(user=faculty_user, role='FACULTY')
        self.faculty.user = faculty_user
        self.faculty.save()
        outsider = User.objects.create_user('unlinked-faculty')
        m.Profile.objects.create(user=outsider, role='FACULTY')
        publish(self.schedule, self.admin)
        self.assertFalse(m.ScheduleNotification.objects.filter(user=outsider).exists())
        other = m.Faculty.objects.create(department=self.department, employee_id='OTHER-NOTICE', full_name='Other Teacher')
        replacement = m.Schedule.objects.create(term=self.term, name='Changed teaching')
        for entry in self.entries:
            replacement.entries.create(assignment=entry.assignment, faculty_override=other,
                room=entry.room, day=entry.day, start_time=entry.start_time, end_time=entry.end_time)
        publish(replacement, self.admin, replace_confirmed=True)
        notices = visible_notifications(faculty_user)
        self.assertEqual([n.kind for n in notices], ['WITHDRAWN'])
