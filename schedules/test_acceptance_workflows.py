"""Task 8.4: synthetic HTTP workflows across preparation, GA and publication.

These tests complement the detailed constraint/security tests. Successful paths
use real forms, services and GA execution; only the correction fixture deliberately
introduces legacy invalid draft data to exercise the existing repair workflow.
"""
from copy import deepcopy
from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import models as m
from .services.conflicts import schedule_validation_messages
from .services.corrections import placement_suggestions
from .services.generation_lock import acquire


class AcceptanceWorkflowTests(TestCase):
    def create(self, resource, model, **payload):
        before = set(model.objects.values_list('pk', flat=True))
        response = self.client.post(reverse('resource_create', args=[resource]), payload)
        self.assertEqual(response.status_code, 302, response.context and str(response.context.get('form')))
        return model.objects.exclude(pk__in=before).get()

    def setUp(self):
        self.administrator = User.objects.create_user('acceptance-admin')
        m.Profile.objects.create(user=self.administrator, role='ADMIN')
        self.client.force_login(self.administrator)
        self.department = self.create('departments', m.Department, code='SYN', name='Synthetic Computing')
        program = self.create('programs', m.Program, department=self.department.pk, code='SYN', name='Synthetic Program')
        year = self.create('year-levels', m.YearLevel, level=1, label='First Year')
        self.term = self.create('terms', m.AcademicTerm, name='Synthetic First Term', school_year='2026-2027',
                                starts_on='2026-08-01', ends_on='2026-12-01', is_active='on')
        self.course = self.create('subjects', m.Subject, department=self.department.pk, code='SYN101',
                                  title='Synthetic Computing Fundamentals', units=2, lecture_hours=1,
                                  lab_hours=1, required_room_type='LECTURE')
        credential = self.create('credentials', m.Credential, name='Synthetic Computing Qualification')
        self.create('subject-credential-requirements', m.SubjectCredentialRequirement,
                    subject=self.course.pk, required_credential=credential.pk)
        self.faculty_users, self.students, self.faculty, self.sections, self.parents = [], [], [], [], []
        for index in (1, 2):
            faculty_user = User.objects.create_user(f'acceptance-faculty-{index}')
            m.Profile.objects.create(user=faculty_user, role='FACULTY')
            teacher = self.create('faculty', m.Faculty, user=faculty_user.pk, department=self.department.pk,
                                  employee_id=f'SYN{index}', full_name=f'Synthetic Teacher {index}', max_weekly_hours=12)
            self.create('faculty-credentials', m.FacultyCredential, faculty=teacher.pk, credential=credential.pk,
                        issued_on='2026-01-01', expires_on='2027-01-01', issued_by='Synthetic School')
            section = self.create('sections', m.Section, program=program.pk, year_level=year.pk,
                                  name=str(index), size=20)
            student = User.objects.create_user(f'acceptance-student-{index}')
            m.Profile.objects.create(user=student, role='STUDENT')
            self.create('students', m.Student, user=student.pk, section=section.pk,
                        student_number=f'SYN{index}', full_name=f'Synthetic Student {index}')
            parent = self.create('assignments', m.Assignment, term=self.term.pk, subject=self.course.pk,
                                 section=section.pk, faculty=teacher.pk, **self.meeting_payload())
            self.faculty_users.append(faculty_user)
            self.students.append(student)
            self.faculty.append(teacher)
            self.sections.append(section)
            self.parents.append(parent)
        self.lecture = self.create('rooms', m.Room, name='Synthetic Lecture Room', room_type='LECTURE', capacity=30, is_active='on')
        self.lab = self.create('rooms', m.Room, name='Synthetic Laboratory', room_type='COMPUTER_LAB', capacity=30, is_active='on')
        for resource in [{'faculty': f.pk} for f in self.faculty] + [{'room': r.pk} for r in (self.lecture, self.lab)]:
            for day in (0, 1):
                self.create('availability', m.Availability, **resource, day=day, start_time='08:00', end_time='16:00', kind='AVAILABLE')
        self.config = self.create('ga-settings', m.GASettings, name='Synthetic Acceptance', population_size=6,
                                  generations=3, mutation_rate=.08, crossover_rate=.85, elitism=1)

    def meeting_payload(self):
        data = {'meetings-TOTAL_FORMS': 2, 'meetings-INITIAL_FORMS': 0,
                'meetings-MIN_NUM_FORMS': 1, 'meetings-MAX_NUM_FORMS': 1000}
        for index, component in enumerate(('LECTURE', 'LABORATORY')):
            data.update({f'meetings-{index}-meeting_index': index + 1,
                         f'meetings-{index}-component': component,
                         f'meetings-{index}-duration_minutes': 60,
                         f'meetings-{index}-required_room_type_override': 'LECTURE' if index == 0 else 'COMPUTER_LAB'})
        return data

    def generate(self, name='Synthetic Generated'):
        before = set(m.GenerationRun.objects.values_list('pk', flat=True))
        response = self.client.post(reverse('generate_schedule'),
            {'term': self.term.pk, 'settings': self.config.pk, 'name': name, 'seed': 1729})
        run = m.GenerationRun.objects.exclude(pk__in=before).get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(run.status, 'SUCCEEDED')
        self.assertEqual(schedule_validation_messages(run.schedule), [])
        self.assertEqual(run.schedule.status, 'DRAFT')
        self.assertEqual(run.schedule.entries.count(), 4)
        for entry in run.schedule.entries.select_related('assignment', 'room'):
            entry.full_clean()
            self.assertIn(entry.day, (0, 1))
            self.assertGreaterEqual(entry.start_time, time(8))
            self.assertLessEqual(entry.end_time, time(16))
            self.assertEqual(entry.room_id, self.lecture.pk if entry.assignment.component == 'LECTURE' else self.lab.pk)
        return run

    @staticmethod
    def placements(schedule):
        return list(schedule.entries.order_by('assignment_id').values_list('assignment_id', 'room_id', 'day', 'start_time', 'end_time'))

    def test_preparation_generation_publication_copy_correction_and_private_timetables(self):
        first, repeat = self.generate(), self.generate('Synthetic Repeat')
        self.assertEqual(self.placements(first.schedule), self.placements(repeat.schedule))
        self.assertEqual(first.reproducibility['inputs'], repeat.reproducibility['inputs'])
        self.assertEqual(first.reproducibility['parameters'], repeat.reproducibility['parameters'])
        self.assertEqual(first.reproducibility['seed'], 1729)
        self.assertEqual(first.reproducibility['outcome']['best_hard_violations'], 0)
        self.assertEqual(first.reproducibility['outcome']['best_soft_score'], first.schedule.fitness_score)
        original = first.schedule
        self.assertEqual(self.client.post(reverse('publish_schedule', args=[original.pk])).status_code, 302)
        original.refresh_from_db()
        self.assertEqual(original.status, 'PUBLISHED')
        snapshot = deepcopy(original.snapshot.data)
        original_placements = self.placements(original)
        self.assertEqual(original.edit_audits.count(), 1)
        for user in (self.students[0], self.faculty_users[0]):
            self.client.force_login(user)
            browse = self.client.get(reverse('browse_schedules'))
            self.assertEqual(browse.status_code, 200)
            page = self.client.get(reverse('schedule_detail', args=[original.pk]))
            self.assertContains(page, self.course.code)
            self.assertContains(page, self.lecture.name)
            self.assertContains(page, self.lab.name)
            self.assertNotContains(page, self.faculty[1].full_name)
            csv = self.client.get(reverse('export_csv', args=[original.pk]))
            self.assertContains(csv, self.faculty[0].full_name)
            self.assertNotContains(csv, self.faculty[1].full_name)
            pdf = self.client.get(reverse('export_pdf', args=[original.pk]))
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
            self.assertEqual(self.client.get(reverse('schedule_detail', args=[repeat.schedule_id])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('schedule_detail', args=[original.pk])).status_code, 302)
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.post(reverse('copy_schedule_to_draft', args=[original.pk])).status_code, 302)
        copied = m.Schedule.objects.exclude(pk__in=[original.pk, repeat.schedule_id]).get()
        entry = copied.entries.first()
        suggestions = placement_suggestions(entry, self.administrator)
        self.assertTrue(suggestions)
        candidate = suggestions[0]['entry']
        edit_url = reverse('entry_update', args=[copied.pk, entry.pk])
        revision = self.client.get(edit_url).context['form'].initial['revision']
        payload = {'revision': revision, 'assignment': entry.assignment_id, 'room': candidate.room_id,
                   'day': candidate.day, 'start_time': candidate.start_time.strftime('%H:%M'),
                   'end_time': candidate.end_time.strftime('%H:%M')}
        self.assertEqual(self.client.post(edit_url, payload).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual((entry.day, entry.start_time, entry.room_id),
                         (candidate.day, candidate.start_time, candidate.room_id))
        self.assertContains(self.client.post(edit_url, payload), 'changed while you were editing')
        self.assertEqual(copied.edit_audits.count(), 2)
        self.assertEqual(schedule_validation_messages(copied), [])
        remove_url = reverse('entry_remove', args=[copied.pk, entry.pk])
        revision = self.client.get(remove_url).context['revision']
        self.assertEqual(self.client.post(remove_url, {'revision': revision, 'confirm_remove': 'yes'}).status_code, 302)
        self.assertEqual(copied.entries.count(), 3)
        self.assertEqual(m.TeachingAssignment.objects.count(), 4)
        self.assertEqual(m.Assignment.objects.count(), 2)
        self.client.post(reverse('publish_schedule', args=[copied.pk]))
        copied.refresh_from_db()
        self.assertEqual(copied.status, 'DRAFT')
        self.assertEqual(copied.edit_audits.count(), 3)
        self.assertEqual(self.placements(original), original_placements)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=original).data, snapshot)
        self.assertEqual(original.edit_audits.count(), 1)

    def test_infeasible_generation_diagnostics_resource_correction_and_retry(self):
        existing = self.generate().schedule
        before = self.placements(existing)
        edit = reverse('resource_update', args=['rooms', self.lab.pk])
        payload = {'name': self.lab.name, 'room_type': 'COMPUTER_LAB', 'capacity': 1, 'is_active': 'on'}
        self.assertEqual(self.client.post(edit, payload).status_code, 302)
        self.client.post(reverse('generate_schedule'), {'term': self.term.pk, 'settings': self.config.pk,
                                                       'name': 'Synthetic Infeasible', 'seed': 1729})
        failed = m.GenerationRun.objects.get(status='FAILED')
        self.assertIsNone(failed.schedule_id)
        self.assertTrue(failed.issues.exists())
        self.assertEqual(failed.reproducibility['seed'], 1729)
        self.assertIsNotNone(failed.completed_at)
        self.assertEqual(m.Schedule.objects.count(), 1)
        self.assertFalse(m.ScheduleSnapshot.objects.exists())
        self.assertEqual(self.placements(existing), before)
        self.assertEqual(self.client.get(reverse('generation_run_detail', args=[failed.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('generation_error_detail', args=[failed.issues.first().pk])).status_code, 200)
        self.assertEqual(self.client.post(edit, {**payload, 'capacity': 30}).status_code, 302)
        repaired = self.generate('Synthetic Retry')
        self.assertEqual(self.placements(repaired.schedule), before)
        self.assertEqual(m.GenerationRun.objects.get(pk=failed.pk).status, 'FAILED')

    def test_legacy_draft_conflict_repair_manual_rejection_and_publication(self):
        schedule = self.generate().schedule
        lecture = schedule.entries.get(assignment__assignment=self.parents[0], assignment__component='LECTURE')
        lab = schedule.entries.get(assignment__assignment=self.parents[0], assignment__component='LABORATORY')
        # Deliberately malformed legacy draft; successful operations below use HTTP.
        m.ScheduleEntry.objects.filter(pk=lecture.pk).update(day=lab.day, start_time=lab.start_time, end_time=lab.end_time)
        lecture.refresh_from_db()
        issues = schedule_validation_messages(schedule)
        self.assertTrue(any('Faculty conflict' in issue for issue in issues))
        self.assertTrue(any('Section conflict' in issue for issue in issues))
        self.client.post(reverse('publish_schedule', args=[schedule.pk]))
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'DRAFT')
        edit = reverse('entry_update', args=[schedule.pk, lecture.pk])
        self.assertContains(self.client.get(reverse('schedule_detail', args=[schedule.pk])), edit)
        token = self.client.get(edit).context['form'].initial['revision']
        before = self.placements(schedule)
        response = self.client.post(edit, {'revision': token, 'assignment': lecture.assignment_id,
            'room': self.lab.pk, 'day': 0, 'start_time': '08:00', 'end_time': '08:30'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(self.placements(schedule), before)
        self.assertEqual(schedule.edit_audits.count(), 0)
        suggestions = placement_suggestions(lecture, self.administrator)
        self.assertTrue(suggestions)
        url = reverse('entry_apply_suggestion', args=[schedule.pk, lecture.pk])
        self.client.post(url, {'suggestion': 'invalid-signature'})
        self.assertEqual(self.placements(schedule), before)
        self.assertEqual(self.client.post(url, {'suggestion': suggestions[0]['token']}).status_code, 302)
        self.assertEqual(schedule_validation_messages(schedule), [])
        self.assertEqual(schedule.edit_audits.count(), 1)
        self.assertEqual(self.client.post(reverse('publish_schedule', args=[schedule.pk])).status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'PUBLISHED')
        self.assertEqual(schedule.edit_audits.count(), 2)

    def test_invalid_preparation_and_busy_generation_preserve_state_then_retry(self):
        response = self.client.post(reverse('resource_create', args=['sections']),
            {'program': self.sections[0].program_id, 'year_level': self.sections[0].year_level_id, 'name': '1', 'size': 20})
        self.assertContains(response, 'This section already exists')
        self.assertEqual(m.Section.objects.count(), 2)
        parent = self.parents[0]
        extra_section = self.create('sections', m.Section, program=self.sections[0].program_id,
                                    year_level=self.sections[0].year_level_id, name='3', size=20)
        data = self.meeting_payload()
        data['meetings-1-duration_minutes'] = 30
        response = self.client.post(reverse('resource_create', args=['assignments']),
            {'term': self.term.pk, 'subject': self.course.pk, 'section': extra_section.pk,
             'faculty': self.faculty[0].pk, **data})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LABORATORY totals 30')
        self.assertEqual(m.Assignment.objects.count(), 2)
        self.assertEqual(parent.meetings.count(), 2)
        owner = acquire(self.term.pk)
        try:
            response = self.client.post(reverse('generate_schedule'),
                {'term': self.term.pk, 'settings': self.config.pk, 'name': 'Synthetic Competing', 'seed': 1729})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(m.GenerationLease.objects.get(term=self.term).owner, owner.owner)
            self.assertFalse(m.Schedule.objects.exists())
            self.assertFalse(m.GenerationRun.objects.exists())
        finally:
            owner.release()
        self.generate('Synthetic After Release')
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)
