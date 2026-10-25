import json
from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from . import models as m
from .services.form_drafts import object_signature
from .services.ga import GeneticScheduler


class MeetingEditorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('tabs-admin', password='test-password')
        self.client.force_login(self.user)
        dept = m.Department.objects.create(code='CS', name='Computing')
        program = m.Program.objects.create(code='CS', name='CS', department=dept)
        year = m.YearLevel.objects.create(level=1, label='Year 1')
        self.section = m.Section.objects.create(program=program, year_level=year, name='A', size=20)
        self.faculty = m.Faculty.objects.create(department=dept, employee_id='T1', full_name='Teacher')
        self.subject = m.Subject.objects.create(code='CS1', title='Computing', department=dept, lecture_hours=2, lab_hours=1)
        self.term = m.AcademicTerm.objects.create(name='Term', school_year='2026', starts_on=date(2026,1,1), ends_on=date(2026,6,1))
        self.parent = m.Assignment.objects.create(term=self.term, subject=self.subject, section=self.section, faculty=self.faculty)
        self.lecture = m.TeachingAssignment.objects.create(assignment=self.parent, component='LECTURE', meeting_index=1, duration_minutes=120)
        self.lab = m.TeachingAssignment.objects.create(assignment=self.parent, component='LABORATORY', meeting_index=2, duration_minutes=60, required_room_type_override='COMPUTER_LAB')
        self.url = f'/schedules/manage/assignments/{self.parent.pk}/edit/'

    def payload(self):
        data = {'term': str(self.term.pk), 'subject': str(self.subject.pk), 'section': str(self.section.pk), 'faculty': str(self.faculty.pk),
                'meetings-TOTAL_FORMS': '2', 'meetings-INITIAL_FORMS': '2', 'meetings-MIN_NUM_FORMS': '1', 'meetings-MAX_NUM_FORMS': '1000'}
        for i, meeting in enumerate([self.lecture, self.lab]):
            for key in ('id', 'component', 'meeting_index', 'duration_minutes', 'required_room_type_override'):
                data[f'meetings-{i}-{key}'] = str(getattr(meeting, key))
        return data

    def save_draft(self, payload):
        return self.client.post('/schedules/drafts/save/', json.dumps({'resource':'assignments', 'object_pk':str(self.parent.pk), 'payload':payload, 'changed':True}), content_type='application/json')

    def test_course_hour_guidance_and_new_meeting_defaults(self):
        response = self.client.get('/schedules/manage/assignments/new/')
        self.assertContains(response, 'data-meeting-hours')
        self.assertEqual(response.context['form'].meeting_requirements()[str(self.subject.pk)],
                         {'LECTURE': 120, 'LABORATORY': 60})
        meetings = response.context['meetings']
        self.assertEqual(meetings.forms[0]['component'].value(), 'LECTURE')
        self.assertEqual(meetings.empty_form['component'].value(), 'LECTURE')
        response = self.client.get(self.url)
        self.assertEqual(response.context['meetings'].forms[1]['component'].value(), 'LABORATORY')
        data = self.payload()
        data['meetings-1-duration_minutes'] = 'bad'
        response = self.client.post(self.url, data)
        self.assertEqual(response.context['meetings'].forms[1]['component'].value(), 'LABORATORY')

    def test_editor_has_only_existing_meetings_and_one_new_meeting(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-meeting-tabs')
        self.assertEqual(len(response.context['meetings'].forms), 2)
        self.assertEqual(len(self.client.get('/schedules/manage/assignments/new/').context['meetings'].forms), 1)

    def test_new_assignment_draft_restores_and_saves_all_meetings(self):
        data = self.payload()
        self.parent.delete()
        data.update({'meetings-INITIAL_FORMS': '0', 'meetings-0-id': '', 'meetings-1-id': ''})
        response = self.client.post('/schedules/drafts/save/', json.dumps({
            'resource': 'assignments', 'payload': data, 'changed': True,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        url = '/schedules/manage/assignments/new/'
        self.assertEqual(len(self.client.get(url).context['meetings'].forms), 2)
        self.assertFalse(m.Assignment.objects.exists())
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(m.Assignment.objects.get().meetings.count(), 2)
        self.assertEqual(m.TeachingAssignment.objects.get(component='LABORATORY').required_room_type_override, 'COMPUTER_LAB')
        self.assertFalse(m.FormDraft.objects.exists())

    def test_draft_preserves_added_and_removed_meetings_without_saving_them(self):
        data = self.payload()
        data.update({'meetings-TOTAL_FORMS':'3', 'meetings-0-DELETE':'on',
                     'meetings-2-component':'LECTURE','meetings-2-meeting_index':'3','meetings-2-duration_minutes':'120',
                     'meetings-2-required_room_type_override':'LECTURE', 'credential_override_confirm':'yes'})
        self.assertEqual(self.save_draft(data).status_code, 200)
        draft = m.FormDraft.objects.get()
        self.assertNotIn('credential_override_confirm', draft.payload)
        restored = self.client.get(self.url).context['meetings']
        self.assertEqual(len(restored.forms), 3)
        self.assertEqual(restored.forms[2]['duration_minutes'].value(), '120')
        self.assertEqual(self.parent.meetings.count(), 2)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertFalse(m.FormDraft.objects.exists())
        self.assertEqual(list(self.parent.meetings.order_by('meeting_index').values_list('meeting_index', flat=True)), [2,3])
        m.Room.objects.create(name='Lecture', room_type='LECTURE', capacity=30)
        m.Room.objects.create(name='Lab', room_type='COMPUTER_LAB', capacity=30)
        schedule = GeneticScheduler(self.term, m.GASettings(population_size=6, generations=3, elitism=1), seed=42).generate()
        self.assertEqual(schedule.entries.count(), 2)

    def test_invalid_meeting_keeps_values_and_errors(self):
        data = self.payload()
        data['meetings-1-duration_minutes'] = '-1'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['meetings'].forms[1].errors)
        self.assertEqual(response.context['meetings'].forms[0]['duration_minutes'].value(), '120')
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.duration_minutes, 60)

    def test_draft_detects_changes_to_meetings(self):
        self.save_draft(self.payload())
        before = object_signature(self.parent)
        self.lab.duration_minutes = 90
        self.lab.save()
        self.assertNotEqual(before, object_signature(self.parent))
        self.assertContains(self.client.get(self.url), 'changed after this draft began')
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.duration_minutes, 90)

    def test_cannot_remove_last_meeting(self):
        data = self.payload()
        data.update({'meetings-0-DELETE':'on', 'meetings-1-DELETE':'on'})
        response = self.client.post(self.url, data)
        self.assertTrue(response.context['meetings'].non_form_errors())
        self.assertEqual(self.parent.meetings.count(), 2)

    def test_shared_fields_sync_preserves_meeting_settings(self):
        replacement = m.Faculty.objects.create(department=self.faculty.department, employee_id='T2', full_name='Replacement')
        section = m.Section.objects.create(program=self.section.program, year_level=self.section.year_level, name='B', size=20)
        subject = m.Subject.objects.create(department=self.subject.department, code='CS2', title='Next Course', lecture_hours=2, lab_hours=1)
        term = m.AcademicTerm.objects.create(name='Next Term', school_year='2027', starts_on=date(2027,1,1), ends_on=date(2027,6,1))
        before = list(self.parent.meetings.order_by('pk').values_list('pk', 'component', 'meeting_index', 'duration_minutes', 'required_room_type_override'))
        data = self.payload()
        data.update(faculty=str(replacement.pk), section=str(section.pk), subject=str(subject.pk), term=str(term.pk))
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.parent.refresh_from_db()
        self.assertEqual(list(self.parent.meetings.order_by('pk').values_list('pk', 'component', 'meeting_index', 'duration_minutes', 'required_room_type_override')), before)
        for meeting in self.parent.meetings.all():
            self.assertEqual((meeting.faculty_id, meeting.section_id, meeting.subject_id, meeting.term_id),
                             (replacement.pk, section.pk, subject.pk, term.pk))
        self.assertEqual({a.faculty_id for a in GeneticScheduler(term, m.GASettings(), seed=1).assignments}, {replacement.pk})

    def test_shared_edit_validation_failure_rolls_back_parent_and_all_meetings(self):
        subject = m.Subject.objects.create(department=self.subject.department, code='CS2', title='Conflicting Course', lecture_hours=2, lab_hours=1)
        other_faculty = m.Faculty.objects.create(department=self.faculty.department, employee_id='T2', full_name='Other Teacher')
        other = m.Assignment.objects.create(term=self.term, subject=subject, section=self.section, faculty=other_faculty)
        m.TeachingAssignment.objects.create(assignment=other, component='LABORATORY', meeting_index=2, duration_minutes=60)
        data = self.payload()
        data['subject'] = str(subject.pk)
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Assignment was not saved')
        # Model saves also roll back, even without the form's early validation.
        self.parent.subject = subject
        with self.assertRaises(ValidationError):
            self.parent.save()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.subject_id, self.subject.pk)
        self.assertEqual(list(self.parent.meetings.values_list('subject_id', flat=True)), [self.subject.pk, self.subject.pk])
        self.assertEqual(m.TeachingAssignment.objects.count(), 3)

    def test_shared_edits_rejected_for_draft_published_and_archived_references(self):
        replacement = m.Faculty.objects.create(department=self.faculty.department, employee_id='T2', full_name='Replacement')
        room = m.Room.objects.create(name='Protected Room', room_type='LECTURE', capacity=30)
        schedule = m.Schedule.objects.create(term=self.term, name='Protected Schedule')
        entry = m.ScheduleEntry.objects.create(schedule=schedule, assignment=self.lecture, room=room,
                                               day=0, start_time=time(8), end_time=time(10), faculty_override=self.faculty)
        for status in (m.ScheduleStatus.DRAFT, m.ScheduleStatus.PUBLISHED, m.ScheduleStatus.ARCHIVED):
            with self.subTest(status=status):
                schedule.status = status
                from .protection import archive_transition
                with archive_transition():
                    schedule.save(update_fields=['status'])
                data = self.payload()
                data['faculty'] = str(replacement.pk)
                self.assertContains(self.client.post(self.url, data), 'meetings used by a schedule')
                self.parent.refresh_from_db()
                entry.refresh_from_db()
                self.assertEqual(self.parent.faculty_id, self.faculty.pk)
                self.assertEqual(set(self.parent.meetings.values_list('faculty_id', flat=True)), {self.faculty.pk})
                self.assertEqual(entry.faculty_override_id, self.faculty.pk)
                self.assertEqual(entry.assignment_id, self.lecture.pk)

    def test_admin_parent_save_synchronizes_unchanged_meetings(self):
        replacement = m.Faculty.objects.create(department=self.faculty.department, employee_id='T2', full_name='Replacement')
        response = self.client.post(f'/admin/schedules/assignment/{self.parent.pk}/change/', {
            'term': self.term.pk, 'subject': self.subject.pk, 'section': self.section.pk, 'faculty': replacement.pk,
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.parent.meetings.values_list('faculty_id', flat=True)), [replacement.pk, replacement.pk])

    def test_legacy_mismatch_cannot_silently_change_a_scheduled_meeting(self):
        replacement = m.Faculty.objects.create(department=self.faculty.department, employee_id='T2', full_name='Replacement')
        # Reproduce data left behind by H1 before this fix.
        m.Assignment.objects.filter(pk=self.parent.pk).update(faculty=replacement)
        room = m.Room.objects.create(name='Legacy Room', room_type='LECTURE', capacity=30)
        schedule = m.Schedule.objects.create(term=self.term, name='Legacy Published')
        m.ScheduleEntry.objects.create(schedule=schedule, assignment=self.lecture, room=room,
                                        day=0, start_time=time(8), end_time=time(10))
        schedule.status = m.ScheduleStatus.PUBLISHED
        schedule.save(update_fields=["status"])
        data = self.payload()
        data['faculty'] = str(replacement.pk)
        self.assertContains(self.client.post(self.url, data), 'meetings used by a schedule')
        self.lecture.refresh_from_db()
        self.assertEqual(self.lecture.faculty_id, self.faculty.pk)

    def test_scheduled_meeting_cannot_be_removed(self):
        room = m.Room.objects.create(name='R', room_type='LECTURE', capacity=30)
        schedule = m.Schedule.objects.create(term=self.term, name='Existing')
        m.ScheduleEntry.objects.create(schedule=schedule, assignment=self.lecture, room=room, day=0, start_time=time(8), end_time=time(10))
        data = self.payload()
        data.update({'meetings-TOTAL_FORMS':'3', 'meetings-0-DELETE':'on', 'meetings-2-component':'LECTURE',
                     'meetings-2-meeting_index':'3','meetings-2-duration_minutes':'120'})
        self.assertContains(self.client.post(self.url, data), 'already used by a schedule')
        self.assertTrue(m.TeachingAssignment.objects.filter(pk=self.lecture.pk).exists())
