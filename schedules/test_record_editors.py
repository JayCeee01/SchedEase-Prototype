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
