import re

from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.forms import BaseInlineFormSet, inlineformset_factory, modelform_factory
from .models import (
    AcademicTerm,
    Assignment,
    Availability,
    Credential,
    CredentialOverride,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    GenerationIssue,
    Program,
    Room,
    Schedule,
    ScheduleEntry,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    Weekday,
    YearLevel,
)


class DiagnosticFilterForm(forms.Form):
    """Validate diagnostic query values before ORM conversion; no scope expansion."""
    run = forms.UUIDField(required=False, label="Generation run")
    date = forms.DateField(required=False, input_formats=['%Y-%m-%d'])
    category = forms.ChoiceField(required=False, choices=GenerationIssue.Category.choices)
    severity = forms.ChoiceField(required=False, choices=GenerationIssue.Severity.choices)
    status = forms.ChoiceField(required=False, choices=GenerationIssue.Status.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('term', 'subject', 'section', 'faculty', 'room'):
            self.fields[name] = forms.IntegerField(required=False, min_value=1, max_value=2**63 - 1,
                                                    label='Course' if name == 'subject' else name.title())


MODEL_FORMS = {
    "departments": modelform_factory(Department, fields=["code", "name"]),
    "programs": modelform_factory(Program, fields=["department", "code", "name"]),
    "year-levels": modelform_factory(YearLevel, fields=["level", "label"]),
    "sections": modelform_factory(Section, fields=["program", "year_level", "name", "size", "adviser"]),
    "subjects": modelform_factory(Subject, fields=["code", "title", "department", "units", "lecture_hours", "lab_hours", "required_room_type"], labels={"code": "Course Code", "title": "Course Description", "lecture_hours": "Required Lecture Hours", "lab_hours": "Required Lab Hours"}),
    "credentials": modelform_factory(Credential, fields=["name", "description"]),
    "faculty-credentials": modelform_factory(FacultyCredential, fields=["faculty", "credential", "issued_by", "issued_on", "expires_on", "notes"], widgets={"issued_on": forms.DateInput(attrs={"type": "date"}), "expires_on": forms.DateInput(attrs={"type": "date"})}),
    "subject-credential-requirements": modelform_factory(SubjectCredentialRequirement, fields=["subject", "required_credential", "acceptable_equivalents", "notes"], labels={"subject": "Course"}),
    "faculty": modelform_factory(Faculty, fields=["user", "department", "employee_id", "full_name", "max_weekly_hours"]),
    "students": modelform_factory(Student, fields=["user", "section", "student_number", "full_name"]),
    "rooms": modelform_factory(Room, fields=["name", "room_type", "capacity", "is_active"]),
    "terms": modelform_factory(AcademicTerm, fields=["name", "school_year", "starts_on", "ends_on", "is_active"], widgets={"starts_on": forms.DateInput(attrs={"type": "date"}), "ends_on": forms.DateInput(attrs={"type": "date"})}),
    "assignments": modelform_factory(Assignment, fields=["term", "subject", "faculty", "section"]),
    "availability": modelform_factory(Availability, fields=["faculty", "room", "section", "day", "start_time", "end_time", "kind"], widgets={"start_time": forms.TimeInput(attrs={"type": "time"}), "end_time": forms.TimeInput(attrs={"type": "time"})}),
    "ga-settings": modelform_factory(GASettings, fields=["name", "population_size", "generations", "mutation_rate", "crossover_rate", "elitism"]),
    "schedules": modelform_factory(Schedule, fields=["term", "name"]),
    "credential-overrides": modelform_factory(CredentialOverride, fields=["assignment", "subject", "faculty", "reason", "missing_credentials"], labels={"subject": "Course"}),
}


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["program", "year_level", "name", "size", "adviser"]
        labels = {"name": "Section Code"}
        help_texts = {"name": "Enter only the identifier, such as 201 or 202."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program"].widget.attrs["data-section-program"] = ""
        self.fields["year_level"].widget.attrs["data-section-year"] = ""
        self.fields["name"].widget.attrs["data-section-code"] = ""
        self.fields["year_level"].label_from_instance = lambda item: f"{item.level} — {item.label}"

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get("program")
        year_level = cleaned.get("year_level")
        name = cleaned.get("name")
        if program and year_level and name:
            normalized = re.sub(r"\s+", " ", name.strip().upper())
            full_name = re.fullmatch(
                rf"{re.escape(program.code)}\s+{year_level.level}-([A-Z0-9][A-Z0-9_-]*)",
                normalized,
                flags=re.IGNORECASE,
            )
            cleaned["name"] = full_name.group(1).upper() if full_name else normalized
            if Section.objects.filter(
                program=program, year_level=year_level, name__iexact=cleaned["name"]
            ).exclude(pk=self.instance.pk).exists():
                self.add_error("name", "This section already exists.")
        return cleaned


MODEL_FORMS["sections"] = SectionForm


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["term", "subject", "section", "faculty"]
        labels = {"subject": "Course"}


class AssignmentMeetingForm(forms.ModelForm):
    class Meta:
        model = TeachingAssignment
        fields = ["meeting_index", "component", "duration_minutes", "required_room_type_override"]
        labels = {"component": "Session Type", "duration_minutes": "Required Duration (minutes)",
                  "required_room_type_override": "Required Room Type"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("component", "meeting_index", "duration_minutes", "required_room_type_override"):
            self.fields[name].required = name in {"component", "meeting_index", "duration_minutes"}

    def clean_component(self):
        return self.cleaned_data.get("component") or TeachingAssignment.Component.GENERAL

    def clean_meeting_index(self):
        return self.cleaned_data.get("meeting_index") or 1

    def clean_duration_minutes(self):
        return self.cleaned_data.get("duration_minutes") or 0


class AssignmentMeetingFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors) or not self.instance.subject_id:
            return
        from .services.meetings import meeting_requirement_errors, meeting_records
        active = [form.instance for form in self.forms if form.cleaned_data and not form.cleaned_data.get("DELETE")]
        errors = meeting_requirement_errors(self.instance.subject, meeting_records(active))
        if errors:
            raise forms.ValidationError([message for _, message in errors])


AssignmentMeetingFormSetFactory = inlineformset_factory(
    Assignment, TeachingAssignment, form=AssignmentMeetingForm, formset=AssignmentMeetingFormSet,
    extra=1, can_delete=True, min_num=1, validate_min=True,
)

MODEL_FORMS["assignments"] = AssignmentForm


class ScheduleGenerationForm(forms.Form):
    seed = forms.IntegerField(required=False, min_value=0, max_value=9223372036854775807,
        label="Random seed (optional)", help_text="Use the same seed and unchanged inputs to repeat an experiment. Leave blank to choose one automatically.")
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all())
    settings = forms.ModelChoiceField(queryset=GASettings.objects.all())
    name = forms.CharField(max_length=120, initial="Generated Schedule")


class ScheduleEntryForm(forms.ModelForm):
    revision = forms.CharField(widget=forms.HiddenInput, error_messages={"required": "Reload this form before saving; its edit revision is missing."})
    class Meta:
        model = ScheduleEntry
        fields = ["assignment", "subject_override", "section_override", "faculty_override", "component_override", "room", "day", "start_time", "end_time"]
        labels = {"assignment": "Meeting", "subject_override": "Course", "section_override": "Section",
                  "faculty_override": "Faculty", "component_override": "Session Type"}
        help_texts = {"subject_override": "Optional change for this schedule version only.",
                      "section_override": "Optional change for this schedule version only.",
                      "faculty_override": "Optional change for this schedule version only.",
                      "component_override": "Optional change for this schedule version only."}
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, defer_credential_review=False, revision_user=None, **kwargs):
        self.defer_credential_review = defer_credential_review
        super().__init__(*args, **kwargs)
        if revision_user is not None and not self.is_bound:
            from .services.manual_edits import revision_token
            self.initial["revision"] = revision_token(self.instance.schedule, revision_user, self.instance if self.instance.pk else None)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial.setdefault("subject_override", self.instance.effective_subject)
            self.initial.setdefault("section_override", self.instance.effective_section)
            self.initial.setdefault("faculty_override", self.instance.effective_faculty)
            self.initial.setdefault("component_override", self.instance.effective_component)

    def _update_errors(self, errors):
        # Admin views review qualification explicitly, then run full validation
        # again inside the save transaction. All other model errors stay visible.
        if self.defer_credential_review:
            error_dict = errors.error_dict if hasattr(errors, "error_dict") else {"__all__": errors.error_list}
            retained = {key: [error for error in values if error.code != "credential_qualification"]
                        for key, values in error_dict.items()}
            retained = {key: values for key, values in retained.items() if values}
            if not retained:
                return
            errors = ValidationError(retained)
        super()._update_errors(errors)


class ScheduleSearchForm(forms.Form):
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all(), required=False)
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False)
    program = forms.ModelChoiceField(queryset=Program.objects.all(), required=False)
    year_level = forms.ModelChoiceField(queryset=YearLevel.objects.all(), required=False)
    section = forms.ModelChoiceField(queryset=Section.objects.all(), required=False)
    subject = forms.ModelChoiceField(queryset=Subject.objects.all(), required=False, label="Course")


class ScheduleEntryFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={
        "type": "search", "placeholder": "Section, course, faculty, or room", "data-schedule-live-filter": "true",
    }))
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False)
    program = forms.ModelChoiceField(queryset=Program.objects.all(), required=False)
    year_level = forms.ModelChoiceField(queryset=YearLevel.objects.all(), required=False)
    section = forms.ModelChoiceField(queryset=Section.objects.all(), required=False)
    faculty = forms.ModelChoiceField(queryset=Faculty.objects.all(), required=False)
    room = forms.ModelChoiceField(queryset=Room.objects.all(), required=False)
    day = forms.ChoiceField(choices=[("", "All days"), *Weekday.choices], required=False)
    component = forms.ChoiceField(
        choices=[("", "All class types"), *TeachingAssignment.Component.choices], required=False, label="Lecture/Laboratory Type"
    )


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    def clean(self):
        identifier = self.cleaned_data.get("username", "")
        if "@" in identifier:
            user = get_user_model().objects.filter(email__iexact=identifier).first()
            if user:
                self.cleaned_data["username"] = user.get_username()
        return super().clean()
