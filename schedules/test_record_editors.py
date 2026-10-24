"""Shared editor presentation contracts, without changing application validation."""
from types import SimpleNamespace
from django import forms
from django.contrib.auth.models import AnonymousUser
from django.forms import formset_factory
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class SampleEditorForm(forms.Form):
    name = forms.CharField(help_text='Existing guidance')
    identity = forms.CharField(widget=forms.HiddenInput, initial='preserved-id')
    reference = forms.CharField(required=False, widget=forms.TextInput(attrs={'readonly': True}))
    unavailable = forms.CharField(required=False, disabled=True, initial='Retained value')


class RecordEditorPresentationTests(SimpleTestCase):
    def render_editor(self, template, **context):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        return render_to_string(template, context, request=request)

    def test_create_and_edit_share_named_form_and_existing_actions(self):
        for title, mode in [('New rooms', 'Create'), ('Edit Room A', 'Edit')]:
            with self.subTest(title=title):
                html = self.render_editor('schedules/form.html', form=SampleEditorForm(), title=title,
                                          draft_resource='rooms', tooltip_context='rooms')
                self.assertIn(f'<h1 id="record-editor-title">{title}</h1>', html)
                self.assertIn(mode, html)
                self.assertIn('aria-labelledby="record-editor-title"', html)
                self.assertIn('record-editor--standard', html)
                self.assertIn('toolbar form-actions', html)
                self.assertIn('href="/schedules/manage/rooms/"', html)
                self.assertIn('name="csrfmiddlewaretoken"', html)
                self.assertIn('name="identity" value="preserved-id"', html)
                self.assertIn('readonly', html)
                self.assertIn('disabled', html)
                self.assertIn('data-form-draft', html)
                self.assertIn('Existing guidance', html)

    def test_bound_invalid_form_keeps_values_errors_and_label_association(self):
        form = SampleEditorForm({'name': '', 'identity': 'submitted-id', 'reference': 'Keep this text'})
        self.assertFalse(form.is_valid())
        html = self.render_editor('schedules/form.html', form=form, title='Edit Room A')
        self.assertIn('This field is required.', html)
        self.assertIn('value="Keep this text"', html)
        self.assertIn('value="submitted-id"', html)
        self.assertIn('for="id_name"', html)
        self.assertIn('id="id_name"', html)
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('required', html)

    def test_assignment_preserves_management_fields_and_specialist_actions(self):
        meetings = formset_factory(SampleEditorForm, can_delete=True)(prefix='meetings')
        html = self.render_editor('schedules/assignment_form.html', form=SampleEditorForm(),
                                  meetings=meetings, assignment=SimpleNamespace(pk=None), title='New Assignment')
        self.assertIn('aria-labelledby="record-editor-title"', html)
        self.assertNotIn('record-editor--standard', html)
        self.assertIn('name="meetings-TOTAL_FORMS"', html)
        self.assertIn('name="meetings-0-DELETE"', html)
        self.assertIn('data-add-meeting', html)
        self.assertIn('data-empty-meeting', html)
        self.assertIn('data-form-draft', html)
        self.assertIn('Save Assignment', html)
        self.assertIn('href="/schedules/manage/assignments/"', html)

    def test_generation_retains_specialist_width_and_action(self):
        html = self.render_editor('schedules/form.html', form=SampleEditorForm(), title='Generate Schedule',
                                  tooltip_context='generate-schedule')
        self.assertNotIn('record-editor--standard', html)
        self.assertIn('data-schedule-generation', html)
        self.assertIn('Import Spreadsheet', html)
        self.assertIn('generation-submit', html)


from django.test import TestCase
from .forms import MODEL_FORMS, AssignmentMeetingForm
from . import models as m


class FormClarityTests(TestCase):
    def test_people_can_be_saved_without_accounts_and_employee_id_is_text(self):
        department = m.Department.objects.create(code="TEST", name="Test")
        program = m.Program.objects.create(department=department, code="TP", name="Test")
        year = m.YearLevel.objects.create(level=1, label="First year")
        section = m.Section.objects.create(program=program, year_level=year, name="A", size=30)
        cases = [
            ("faculty", dict(department=department.pk, employee_id="EMP001A", full_name="Test Faculty", max_weekly_hours=24)),
            ("students", dict(section=section.pk, student_number="00123", full_name="Test Student")),
        ]
        for resource, data in cases:
            form = MODEL_FORMS[resource](data)
            self.assertTrue(form.is_valid(), form.errors)
            record = form.save()
            record.refresh_from_db()
            self.assertIsNone(record.user_id)
            self.assertFalse(form.fields["user"].required)
            self.assertIn("Login account (optional)", form.as_p())
            self.assertIn("link an existing account later", form.as_p())
        self.assertEqual(m.Faculty.objects.get().employee_id, "EMP001A")
        self.assertEqual(m.Student.objects.get().student_number, "00123")

    def test_guidance_renders_in_existing_forms(self):
        self.assertIn("EMP001A", MODEL_FORMS["faculty"]().as_p())
        self.assertIn("90 minutes = 1.5 hours", AssignmentMeetingForm().as_p())
        self.assertIn("every requirement", MODEL_FORMS["subject-credential-requirements"]().as_p())
        self.assertIn("authorized administrator", MODEL_FORMS["credential-overrides"]().as_p())
        self.assertIn("Availability type", MODEL_FORMS["availability"]().as_p())
        self.assertIn("leave Room and Section blank", MODEL_FORMS["availability"]().as_p())

    def test_availability_descriptions_and_validation(self):
        from datetime import time
        from django.core.exceptions import ValidationError
        department = m.Department.objects.create(code="TEST", name="Test")
        faculty = m.Faculty.objects.create(department=department, employee_id="A1", full_name="Test Faculty")
        room = m.Room.objects.create(name="Test Room", room_type="LECTURE", capacity=50)
        for owner in (dict(faculty=faculty), dict(room=room)):
            period = m.Availability(**owner, day=0, start_time=time(9), end_time=time(10), kind="AVAILABLE")
            period.full_clean()
            self.assertIn("Monday 09:00-10:00 - Available", str(period))
            self.assertIn(str(next(iter(owner.values()))), str(period))
            period.end_time = time(9)
            with self.assertRaises(ValidationError):
                period.full_clean()
        invalid = m.Availability(faculty=faculty, room=room, day=0, start_time=time(9), end_time=time(10))
        with self.assertRaises(ValidationError):
            invalid.full_clean()
