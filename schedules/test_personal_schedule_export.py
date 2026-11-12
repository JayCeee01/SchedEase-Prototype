from io import BytesIO
from django.urls import reverse
from openpyxl import load_workbook
from .test_known_defects import SchedulingDefectFixture
from . import test_student_timetable as fixtures
from .services.publication import publish
from . import models as m


class PersonalExportTests(SchedulingDefectFixture):
    setUp = fixtures.StudentTimetableTests.setUp

    def download(self, **params):
        return self.client.get(reverse('personal_schedule_export', args=['xlsx']), dict(schedule=self.schedule.pk, **params))

    def test_student_formats_applied_filters_and_scope(self):
        publish(self.schedule, self.admin)
        self.client.force_login(self.user)
        response = self.download()
        self.assertEqual(response.status_code, 200)
        ws = load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws.title, 'My Schedule')
        self.assertEqual(ws.max_row, 5)
        self.assertIn('Test Student', ws['A2'].value)
        self.assertEqual(ws['B4'].value, 'WEEKLY')
        self.assertEqual(self.download(term=999999).status_code, 404)
        empty = self.download(q='no-match')
        self.assertEqual(load_workbook(BytesIO(empty.content)).active.max_row, 3)
        page = self.client.get(reverse('browse_schedules'), {'schedule':self.schedule.pk,'view':'timetable'})
        self.assertContains(page, 'Export as Excel')
        self.assertContains(page, f'schedule={self.schedule.pk}')
        pdf = self.client.get(reverse('personal_schedule_export', args=['pdf']), {'schedule':self.schedule.pk, 'source':'detail'})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        empty_pdf = self.client.get(reverse('personal_schedule_export', args=['pdf']), {'schedule':self.schedule.pk, 'q':'no-match'})
        self.assertEqual(empty_pdf.status_code, 200)
        self.assertTrue(empty_pdf.content.startswith(b'%PDF'))

    def test_faculty_only_effective_assignments(self):
        profile = self.user.profile
        profile.role = 'FACULTY'
        profile.save()
        self.faculty.user = self.user
        self.faculty.save()
        other = m.Faculty.objects.create(department=self.department, employee_id='EXPORT-OTHER', full_name='Other private teacher')
        entry = self.entries[1]
        entry.faculty_override = other
        entry.save()
        publish(self.schedule, self.admin)
        self.client.force_login(self.user)
        ws = load_workbook(BytesIO(self.download().content)).active
        self.assertEqual(ws.max_row, 4)
        self.assertNotIn('Other private teacher', str(list(ws.values)))
        self.assertIn(self.faculty.full_name, ws['A2'].value)

    def test_draft_unlinked_invalid_and_cross_user(self):
        self.client.force_login(self.user)
        self.assertEqual(self.download().status_code, 404)
        publish(self.schedule, self.admin)
        student = self.user.student
        student.user = None
        student.save()
        self.assertEqual(self.download().status_code, 404)
        self.assertEqual(self.client.get(reverse('personal_schedule_export', args=['xlsx']), {'schedule':'bad'}).status_code, 404)

    def test_both_views_infer_one_schedule_and_preserve_filters(self):
        publish(self.schedule, self.admin)
        self.client.force_login(self.user)
        values = []
        for view in ('table', 'timetable'):
            params = {'view': view, 'q': self.subject.code}
            page = self.client.get(reverse('browse_schedules'), params)
            self.assertContains(page, '<summary>Export Schedule</summary>', count=1)
            self.assertEqual(page.context['export_schedule'].pk, self.schedule.pk)
            self.assertIn('q='+self.subject.code, page.context['view_links']['table'])
            response = self.client.get(reverse('personal_schedule_export', args=['xlsx']), params)
            self.assertEqual(response.status_code, 200)
            values.append(list(load_workbook(BytesIO(response.content)).active.values))
        self.assertEqual(values[0], values[1])
        empty = self.client.get(reverse('browse_schedules'), {'q':'not-found'})
        self.assertContains(empty, 'disabled aria-describedby="export-guidance"')
        self.assertEqual(self.client.get(reverse('personal_schedule_export', args=['xlsx']), {'q':'not-found'}).status_code, 404)

    def test_ambiguous_scope_guidance(self):
        from copy import copy
        publish(self.schedule, self.admin)
        term = copy(self.term)
        term.pk = None
        term.name = 'Another published term'
        term.save()
        other = m.Schedule.objects.create(term=term, name='Another published version')
        parent = m.Assignment.objects.create(term=term, subject=self.subject, section=self.section, faculty=self.faculty)
        for entry in self.entries:
            assignment = m.TeachingAssignment.objects.create(assignment=parent,
                component=entry.assignment.component, meeting_index=entry.assignment.meeting_index, duration_minutes=60)
            other.entries.create(assignment=assignment, room=entry.room, day=1,
                                 start_time=entry.start_time, end_time=entry.end_time)
        publish(other, self.admin)
        self.client.force_login(self.user)
        page = self.client.get(reverse('browse_schedules'))
        self.assertIsNone(page.context['export_schedule'])
        self.assertContains(page, 'Select a Schedule Version and apply filters')
        self.assertEqual(self.client.get(reverse('personal_schedule_export', args=['xlsx'])).status_code, 404)
        self.assertEqual(self.download().status_code, 200)
