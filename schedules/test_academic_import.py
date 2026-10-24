import csv
import io
import zipfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from . import models as m
from .importers.academic import COLUMNS, read_spreadsheet, run_import, template_bytes
from .services.ga import GeneticScheduler


class AcademicImportTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('import-admin', 'admin@example.test', 'test-pass')
        self.client.force_login(self.admin)
        self.term = m.AcademicTerm.objects.create(name='Import term', school_year='2026', starts_on=date(2026, 1, 1), ends_on=date(2026, 6, 1))
        self.row = dict(department_code='CS', department_name='Computing', program_code='BSCS', program_name='Computer Science',
            year_level='1', year_label='Year 1', section_code='201', section_size='25', course_code='CS101',
            course_description='Programming', units='3.0', lecture_hours='1', lab_hours='1', course_room_type='LECTURE',
            assigned_faculty_id='F001', faculty_name='Ada Teacher', faculty_max_hours='12',
            faculty_credentials='Computing', course_credentials='Computing', room_name='R101', room_type='LECTURE', room_capacity='30',
            component='LECTURE', meeting_index='1', duration_minutes='60', meeting_room_type='LECTURE')
        # Qualification now requires a documented issue date. The spreadsheet
        # format supplies credential names only; dated records are prepared first.
        department = m.Department.objects.create(code='CS', name='Computing')
        faculty = m.Faculty.objects.create(department=department, employee_id='F001', full_name='Ada Teacher', max_weekly_hours=12)
        credential = m.Credential.objects.create(name='Computing')
        m.FacultyCredential.objects.create(faculty=faculty, credential=credential, issued_on=date(2025, 1, 1))
        self.rows = [self.row, {**self.row, 'room_name': 'Lab', 'room_type': 'COMPUTER_LAB',
                              'component': 'LABORATORY', 'meeting_index': '2', 'meeting_room_type': 'COMPUTER_LAB'}]

    def payload(self, rows=None):
        headers = list(COLUMNS)
        return {'headers': headers, 'rows': [{'number': i, 'values': [row.get(k, '') for k in headers]}
                                           for i, row in enumerate(rows if rows is not None else self.rows, 2)]}

    def preview(self, rows=None, policy='skip'):
        return run_import(self.payload(rows), list(COLUMNS), self.term, policy)

    def commit(self, rows=None, policy='skip'):
        result = self.preview(rows, policy)
        self.assertEqual(result['errors'], [])
        return run_import(self.payload(rows), list(COLUMNS), self.term, policy, True, result['signature'])

    def test_preview_rolls_back_then_commit_preserves_relationships_and_ga(self):
        result = self.preview()
        self.assertEqual(result['errors'], [])
        self.assertGreater(result['counts']['created'], 0)
        self.assertEqual(m.Subject.objects.count(), 0)
        self.commit()
        self.assertEqual(m.Department.objects.count(), 1)
        self.assertEqual(m.Program.objects.get().department.code, 'CS')
        self.assertEqual(m.Section.objects.get().size, 25)
        self.assertEqual(m.FacultyCredential.objects.count(), 1)
        parent = m.Assignment.objects.get()
        self.assertEqual(parent.meetings.count(), 2)
        self.assertEqual(set(parent.meetings.values_list('component', flat=True)), {'LECTURE', 'LABORATORY'})
        self.assertEqual(m.Schedule.objects.count(), 0)
        settings = m.GASettings.objects.create(population_size=6, generations=3, elitism=1)
        scheduler = GeneticScheduler(self.term, settings, seed=42)
        self.assertEqual(scheduler.preflight_issues(), [])
        schedule = scheduler.generate('Imported requirements test')
        self.assertEqual(schedule.entries.count(), 2)

    def test_repeated_import_is_idempotent(self):
        self.commit()
        result = self.commit()
        self.assertEqual(result['counts'].get('created', 0), 0)
        self.assertEqual(m.Assignment.objects.count(), 1)
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)

    def test_skip_preserves_and_update_changes_only_supplied_attributes(self):
        self.commit()
        changed = [{**row, 'course_description': 'New title'} for row in self.rows]
        self.commit(changed)
        self.assertEqual(m.Subject.objects.get().title, 'Programming')
        self.commit(changed, 'update')
        self.assertEqual(m.Subject.objects.get().title, 'New title')

    def test_missing_capacity_not_invented_and_failure_is_atomic(self):
        rows = [self.row, {**self.rows[1], 'room_capacity': ''}]
        result = self.preview(rows)
        self.assertTrue(any('capacity' in e for e in result['errors']))
        result = run_import(self.payload(rows), list(COLUMNS), self.term, commit=True, expected_signature=result['signature'])
        self.assertTrue(result['errors'])
        self.assertFalse(m.Subject.objects.exists())
        self.assertFalse(m.Room.objects.exists())

    def test_invalid_types_and_credentials(self):
        for key, value in [('units', 'abc'), ('section_size', '-1'), ('component', 'NOT_A_COMPONENT'), ('duration_minutes', '900')]:
            with self.subTest(key=key):
                result = self.preview([{**row, key: value} for row in self.rows])
                self.assertTrue(result['errors'])
                self.assertFalse(m.Subject.objects.exists())
        m.FacultyCredential.objects.all().delete()
        result = self.preview([{**row, 'faculty_credentials': ''} for row in self.rows])
        self.assertTrue(any('missing required credential' in e for e in result['errors']))

    def test_import_does_not_invent_dates_or_approve_undated_credentials(self):
        m.FacultyCredential.objects.all().delete()
        result = self.preview()
        self.assertTrue(any('missing issue date' in error for error in result['errors']))
        self.assertFalse(m.FacultyCredential.objects.exists())
        self.assertFalse(m.Subject.objects.exists())

    def test_repeat_import_preserves_matching_administrator_overrides(self):
        self.commit()
        m.FacultyCredential.objects.update(expires_on=date(2025, 12, 31))
        for meeting in m.TeachingAssignment.objects.all():
            m.CredentialOverride.objects.create(assignment=meeting, subject=meeting.subject, faculty=meeting.faculty,
                admin_user=self.admin, reason='Explicit term exception', missing_credentials='Expired credential')
        self.commit()
        self.assertEqual(m.CredentialOverride.objects.count(), 2)

    def test_meeting_totals_and_indexes(self):
        result = self.preview([self.row])
        self.assertTrue(any('LABORATORY totals' in e for e in result['errors']))
        result = self.preview([self.row, {**self.rows[1], 'meeting_index': '1'}])
        self.assertTrue(any('Each meeting in this assignment must have a different meeting number.' in e for e in result['errors']))

    def test_identical_duplicate_row_is_counted_once_conflicting_duplicate_rejected(self):
        result = self.commit(self.rows + [self.row])
        self.assertTrue(any('duplicate meeting' in w for w in result['warnings']))
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)
        result = self.preview(self.rows + [{**self.row, 'section_size': '99'}])
        self.assertTrue(result['errors'])

    def test_stale_confirmation_rolls_back(self):
        result = self.preview()
        m.Department.objects.filter(code='CS').update(name='Changed elsewhere')
        with self.assertRaisesMessage(ValueError, 'changed since preview'):
            run_import(self.payload(), list(COLUMNS), self.term, commit=True, expected_signature=result['signature'])
        self.assertEqual(m.Department.objects.get().name, 'Changed elsewhere')
        self.assertFalse(m.Subject.objects.exists())

    def test_reference_data_does_not_create_schedule_or_constraints(self):
        self.commit([{**row, 'reference_day': 'Monday', 'reference_start': '08:00', 'reference_room': 'Ghost room',
                      'reference_faculty': 'Someone else'} for row in self.rows])
        self.assertFalse(m.ScheduleEntry.objects.exists())
        self.assertFalse(m.Availability.objects.exists())
        self.assertFalse(m.Room.objects.filter(name='Ghost room').exists())

    def test_explicit_availability_import(self):
        self.commit([{**row, 'availability_owner': 'FACULTY', 'availability_day': 'Monday',
            'availability_start': '07:00', 'availability_end': '08:00', 'availability_kind': 'UNAVAILABLE'} for row in self.rows])
        self.assertEqual(m.Availability.objects.count(), 1)
        self.assertEqual(m.Availability.objects.get().faculty.employee_id, 'F001')

    def test_file_validation_csv_and_xlsx(self):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        writer.writerow([self.row.get(k, '') for k in COLUMNS])
        result = read_spreadsheet(SimpleUploadedFile('data.csv', stream.getvalue().encode()))
        self.assertEqual(len(result['rows']), 1)
        with self.assertRaisesMessage(ValueError, 'no data rows'):
            read_spreadsheet(SimpleUploadedFile('data.xlsx', template_bytes(True, include_samples=False)))
        for name, content in [('data.xls', b'bad'), ('data.xlsx', b'bad'), ('data.csv', b'a,a\n1,2'), ('data.csv', b'a\n1,2')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_spreadsheet(SimpleUploadedFile(name, content))
        with self.assertRaisesMessage(ValueError, '5 MB'):
            read_spreadsheet(SimpleUploadedFile('large.csv', b'a' * (5 * 1024 * 1024 + 1)))

    def test_xlsx_values_and_formula_rejection(self):
        def workbook(cell):
            source = zipfile.ZipFile(io.BytesIO(template_bytes(True, include_samples=False)))
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as dest:
                for name in source.namelist():
                    content = source.read(name)
                    if name.endswith('sheet1.xml'):
                        content = content.replace(b'</sheetData>', ('<row r="2">' + cell + '</row></sheetData>').encode())
                    dest.writestr(name, content)
            return SimpleUploadedFile('data.xlsx', output.getvalue())
        parsed = read_spreadsheet(workbook('<c r="A2" t="inlineStr"><is><t>CS</t></is></c>'))
        self.assertEqual(parsed['rows'][0]['values'][0], 'CS')
        with self.assertRaisesMessage(ValueError, 'formulas'):
            read_spreadsheet(workbook('<c r="A2"><f>1+1</f><v>2</v></c>'))

    def test_mapping_validation(self):
        with self.assertRaisesMessage(ValueError, 'required columns'):
            run_import(self.payload(), [''] * len(COLUMNS), self.term)
        with self.assertRaisesMessage(ValueError, 'only once'):
            run_import(self.payload(), ['course_code'] * len(COLUMNS), self.term)

    def test_full_http_workflow_and_replay(self):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for row in self.rows:
            writer.writerow([row.get(k, '') for k in COLUMNS])
        response = self.client.post(reverse('academic_import'), {'term': self.term.pk, 'spreadsheet': SimpleUploadedFile('data.csv', stream.getvalue().encode())})
        self.assertEqual(response.status_code, 302)
        batch = m.AcademicImport.objects.get()
        url = reverse('academic_import_review', args=[batch.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        data = {f'column_{i}': key for i, key in enumerate(COLUMNS)}
        response = self.client.post(url, {**data, 'policy': 'skip', 'faculty_confirm': 'on', 'action': 'preview'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ready to Import')
        batch.refresh_from_db()
        self.assertTrue(batch.preview_signature)
        response = self.client.post(url, {'action': 'confirm', 'signature': batch.preview_signature})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)
        self.client.post(url, {'action': 'confirm', 'signature': batch.preview_signature})
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)

    def test_authorization_owner_expiry_and_csrf(self):
        batch = m.AcademicImport.objects.create(user=self.admin, payload={**self.payload(), 'term_id': self.term.pk})
        url = reverse('academic_import_review', args=[batch.pk])
        user = get_user_model().objects.create_user('student', password='test')
        self.client.force_login(user)
        for endpoint in [reverse('academic_import'), url, reverse('academic_import_template', args=['csv'])]:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
        other = get_user_model().objects.create_superuser('other', 'other@example.test', 'test')
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        m.AcademicImport.objects.filter(pk=batch.pk).update(created_at=timezone.now() - timedelta(hours=3))
        self.assertRedirects(self.client.get(url), reverse('academic_import'))
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('academic_import')).status_code, 403)

    def test_update_requires_explicit_approval(self):
        self.commit()
        payload = {**self.payload([{**r, 'course_description': 'Updated'} for r in self.rows]), 'term_id': self.term.pk}
        result = run_import(payload, list(COLUMNS), self.term, 'update')
        payload.update(mapping=list(COLUMNS), policy='update')
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature=result['signature'])
        url = reverse('academic_import_review', args=[batch.pk])
        response = self.client.post(url, {'action': 'confirm', 'signature': result['signature']})
        self.assertContains(response, 'Tick the approval box')
        self.assertEqual(m.Subject.objects.get().title, 'Programming')
        self.assertEqual(self.client.post(url, {'action': 'confirm', 'signature': result['signature'], 'approve_updates': 'yes'}).status_code, 302)
        self.assertEqual(m.Subject.objects.get().title, 'Updated')

    def scheduled(self):
        self.commit()
        settings = m.GASettings.objects.create(population_size=6, generations=3, elitism=1)
        return GeneticScheduler(self.term, settings, seed=42).generate('Existing schedule')

    def test_shared_update_cannot_invalidate_existing_schedule(self):
        self.scheduled()
        result = self.preview([{**row, 'room_capacity': '1'} for row in self.rows], 'update')
        self.assertTrue(any('capacity is too small' in e for e in result['errors']))
        self.assertEqual(set(m.Room.objects.values_list('capacity', flat=True)), {30})

    def test_used_meeting_cannot_be_resized(self):
        self.scheduled()
        result = self.preview([{**row, 'duration_minutes': '120'} for row in self.rows], 'update')
        self.assertTrue(any('used by a schedule' in e for e in result['errors']))
        self.assertEqual(set(m.TeachingAssignment.objects.values_list('duration_minutes', flat=True)), {60})

    def test_new_unavailability_cannot_invalidate_scheduled_entry(self):
        schedule = self.scheduled()
        entry = schedule.entries.first()
        result = self.preview([{**row, 'availability_owner': 'FACULTY', 'availability_day': str(entry.day),
            'availability_start': '07:00', 'availability_end': '19:00', 'availability_kind': 'UNAVAILABLE'} for row in self.rows])
        self.assertTrue(any('Faculty is unavailable' in e for e in result['errors']))
        self.assertFalse(m.Availability.objects.exists())

    def test_downloaded_templates_have_valid_lecture_and_lab_examples(self):
        for kind in ('csv', 'xlsx'):
            response = self.client.get(reverse('academic_import_template', args=[kind]))
            self.assertEqual(response.status_code, 200)
            payload = read_spreadsheet(SimpleUploadedFile('template.' + kind, response.content))
            self.assertEqual(len(payload['rows']), 2)
            result = run_import(payload, payload['headers'], self.term)
            self.assertEqual(result['errors'], [])
            self.assertFalse(m.Subject.objects.exists())

    def test_structured_errors_highlight_cells_filter_and_download(self):
        rows = [self.row, {**self.rows[1], 'room_capacity': ''}]
        payload = {**self.payload(rows), 'term_id': self.term.pk, 'filename': 'incomplete.csv'}
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload)
        url = reverse('academic_import_review', args=[batch.pk])
        fields = {f'column_{i}': key for i, key in enumerate(COLUMNS)}
        response = self.client.post(url, {**fields, 'action': 'preview', 'policy': 'skip', 'faculty_confirm': 'on'})
        self.assertContains(response, 'Download Error Report')
        self.assertContains(response, 'import-cell-error')
        self.assertNotContains(response, 'Continue to Confirm')
        batch.refresh_from_db()
        self.assertEqual(batch.payload['preview']['issues'][0]['columns'], ['room_capacity'])
        response = self.client.get(url + '?filter=errors')
        self.assertEqual([r['number'] for r in response.context['preview_rows']], [3])
        self.assertEqual(response.context['ready_count'], 0)
        report = self.client.get(reverse('academic_import_errors', args=[batch.pk]))
        self.assertEqual(report.status_code, 200)
        self.assertIn('Number of seats', report.content.decode('utf-8-sig'))
        self.assertFalse(m.Room.objects.exists())

    def test_review_navigation_and_success_summary(self):
        payload = {**self.payload(), 'term_id': self.term.pk, 'filename': 'classes.csv', 'mapping': list(COLUMNS), 'policy': 'skip'}
        result = self.preview()
        payload['preview'] = result
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature=result['signature'])
        url = reverse('academic_import_review', args=[batch.pk])
        self.assertEqual(self.client.get(url).context['stage'], 'review')
        self.assertEqual(self.client.get(url + '?step=mapping').context['stage'], 'mapping')
        self.assertContains(self.client.get(url + '?step=confirm'), 'Confirm Import')
        response = self.client.post(url, {'action': 'confirm', 'signature': result['signature']}, follow=True)
        self.assertContains(response, 'Your records have been saved')
        self.assertContains(response, reverse('resource_list', args=['assignments']))
        self.assertEqual(response.context['result']['counts'], result['counts'])
        self.assertFalse(m.Schedule.objects.exists())

    def test_invalid_mapping_revokes_previous_confirmation(self):
        payload = {**self.payload(), 'term_id': self.term.pk, 'mapping': list(COLUMNS), 'policy': 'skip'}
        result = self.preview()
        payload['preview'] = result
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature=result['signature'])
        url = reverse('academic_import_review', args=[batch.pk])
        self.client.post(url, {'action': 'preview', 'policy': 'skip', 'faculty_confirm': 'on'})
        batch.refresh_from_db()
        self.assertFalse(batch.preview_signature)
        self.client.post(url, {'action': 'confirm', 'signature': result['signature']})
        self.assertFalse(m.Subject.objects.exists())

    def test_large_supported_file_and_paginated_preview(self):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for _ in range(1000):
            writer.writerow([self.row.get(k, '') for k in COLUMNS])
        payload = read_spreadsheet(SimpleUploadedFile('large.csv', stream.getvalue().encode()))
        payload.update(term_id=self.term.pk, mapping=list(COLUMNS), policy='skip', preview={
            'total': 1000, 'actions': [], 'errors': [], 'issues': [], 'warnings': [], 'counts': {}, 'signature': 'example'})
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature='example')
        response = self.client.get(reverse('academic_import_review', args=[batch.pk]) + '?page=20')
        self.assertEqual(response.context['page_count'], 20)
        self.assertEqual(len(response.context['preview_rows']), 50)
        self.assertEqual(response.context['preview_rows'][-1]['number'], 1001)
        writer.writerow([self.row.get(k, '') for k in COLUMNS])
        with self.assertRaisesMessage(ValueError, '1,000'):
            read_spreadsheet(SimpleUploadedFile('too-many.csv', stream.getvalue().encode()))

    def test_report_owner_permissions_and_formula_safety(self):
        batch = m.AcademicImport.objects.create(user=self.admin, payload={'preview': {
            'issues': [{'row': 2, 'columns': ['course_code'], 'problem': '=HYPERLINK("bad")'}]}})
        url = reverse('academic_import_errors', args=[batch.pk])
        report = self.client.get(url).content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", report)
        other = get_user_model().objects.create_superuser('report-admin', password='test')
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_revoked_preview_cannot_appear_ready_after_reload(self):
        result = self.preview()
        payload = {**self.payload(), 'term_id': self.term.pk, 'mapping': list(COLUMNS),
                   'policy': 'skip', 'preview': result}
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature=result['signature'])
        url = reverse('academic_import_review', args=[batch.pk])
        fields = {f'column_{i}': 'course_code' for i in range(len(COLUMNS))}
        self.client.post(url, {**fields, 'action': 'preview', 'policy': 'skip', 'faculty_confirm': 'on'})
        response = self.client.get(url + '?step=confirm')
        self.assertEqual(response.context['stage'], 'mapping')
        self.assertNotContains(response, 'Continue to Confirm')
        self.assertFalse(m.Subject.objects.exists())

    def test_missing_update_approval_stays_on_confirmation(self):
        self.commit()
        result = self.preview(policy='update')
        payload = {**self.payload(), 'term_id': self.term.pk, 'mapping': list(COLUMNS),
                   'policy': 'update', 'preview': result}
        batch = m.AcademicImport.objects.create(user=self.admin, payload=payload, preview_signature=result['signature'])
        url = reverse('academic_import_review', args=[batch.pk])
        response = self.client.post(url, {'action': 'confirm', 'signature': result['signature']})
        self.assertEqual(response.context['stage'], 'confirm')
        self.assertContains(response, 'Tick the approval box')
        self.assertContains(response, 'Saving your records.')
        batch.refresh_from_db()
        self.assertFalse(batch.completed_at)
        self.assertTrue(batch.preview_signature)

    def test_mapping_summary_and_stage_specific_feedback(self):
        batch = m.AcademicImport.objects.create(user=self.admin, payload={**self.payload(), 'term_id': self.term.pk})
        response = self.client.get(reverse('academic_import_review', args=[batch.pk]))
        self.assertEqual(response.context['matched_columns'], len(COLUMNS))
        self.assertFalse(response.context['mapping_needs_review'])
        self.assertContains(response, 'No records are being saved yet.')
        self.assertContains(response, 'data-mapping-search')
        self.assertNotContains(response, 'data-column-choices open')
        payload = self.payload()
        payload['headers'][0] = 'Unfamiliar heading'
        batch.payload = {**payload, 'term_id': self.term.pk}
        batch.save()
        response = self.client.get(reverse('academic_import_review', args=[batch.pk]))
        self.assertTrue(response.context['mapping_needs_review'])
        self.assertEqual(response.context['unmatched_columns'], 1)
        self.assertContains(response, 'data-column-choices open')

    def test_H5_extra_component_is_rejected_with_source_row(self):
        rows = [{**row, 'lab_hours': '0'} for row in self.rows]
        result = self.preview(rows)
        self.assertTrue(any('LABORATORY totals 60' in error and 'Row' in error for error in result['errors']))
        self.assertFalse(m.Assignment.objects.exists())

    def test_H7_invalid_durations_rollback(self):
        for duration in ('0', '-1', '0.5', '721'):
            with self.subTest(duration=duration):
                result = self.preview([{**self.row, 'duration_minutes': duration}])
                self.assertTrue(any('duration_minutes' in e for e in result['errors']))
                self.assertFalse(m.Assignment.objects.exists())

    def test_H7_inactive_room_rejected_without_changes(self):
        room = m.Room.objects.create(name='R101', room_type='LECTURE', capacity=30, is_active=False)
        result = self.preview(policy='update')
        self.assertTrue(any('room_name' in e and 'inactive' in e for e in result['errors']))
        self.assertFalse(m.Subject.objects.exists())
        room.refresh_from_db()
        self.assertFalse(room.is_active)

    def test_H2_import_cannot_change_finalized_course_information(self):
        self.commit()
        schedule = m.Schedule.objects.create(term=self.term, name='Official')
        for i, meeting in enumerate(m.TeachingAssignment.objects.all()):
            from datetime import time
            schedule.entries.create(assignment=meeting, room=m.Room.objects.get(room_type=meeting.effective_room_type),
                                    day=i, start_time=time(8), end_time=time(9))
        schedule.status = m.ScheduleStatus.PUBLISHED
        schedule.save(update_fields=['status'])
        result = self.preview([{**row, 'course_description': 'Changed'} for row in self.rows], policy='update')
        self.assertTrue(any('published or archived' in e for e in result['errors']))
        self.assertEqual(m.Subject.objects.get().title, 'Programming')
        self.assertEqual(schedule.entries.count(), 2)

    def test_term_selection_import_creates_separate_assignments_without_reassigning_finalized_data(self):
        self.commit()
        from datetime import time
        schedule = m.Schedule.objects.create(term=self.term, name='Original term')
        for i, meeting in enumerate(m.TeachingAssignment.objects.all()):
            schedule.entries.create(assignment=meeting, room=m.Room.objects.get(room_type=meeting.effective_room_type),
                                    day=i, start_time=time(8), end_time=time(9))
        schedule.status = m.ScheduleStatus.PUBLISHED
        schedule.save(update_fields=['status'])
        original_ids = set(schedule.entries.values_list('assignment_id', flat=True))
        other = m.AcademicTerm.objects.create(name='Next term', school_year='2026', starts_on=date(2026, 7, 1), ends_on=date(2026, 12, 1))
        result = run_import(self.payload(), list(COLUMNS), other)
        self.assertEqual(result['errors'], [])
        saved = run_import(self.payload(), list(COLUMNS), other, commit=True, expected_signature=result['signature'])
        self.assertEqual(saved['errors'], [])
        self.assertEqual(m.TeachingAssignment.objects.filter(term=other).count(), 2)
        self.assertEqual(set(schedule.entries.values_list('assignment_id', flat=True)), original_ids)
        self.assertEqual(set(m.TeachingAssignment.objects.filter(pk__in=original_ids).values_list('term_id', flat=True)), {self.term.pk})
