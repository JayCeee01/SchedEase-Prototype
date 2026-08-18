from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.forms import modelform_factory
from .models import (
    AcademicTerm,
    Availability,
    Credential,
    CredentialOverride,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    Program,
    Room,
    Schedule,
    ScheduleEntry,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
)


MODEL_FORMS = {
    "departments": modelform_factory(Department, fields=["code", "name"]),
    "programs": modelform_factory(Program, fields=["department", "code", "name"]),
    "year-levels": modelform_factory(YearLevel, fields=["level", "label"]),
    "sections": modelform_factory(Section, fields=["program", "year_level", "name", "size", "adviser"]),
    "subjects": modelform_factory(Subject, fields=["code", "title", "department", "units", "lecture_hours", "lab_hours", "required_room_type"]),
    "credentials": modelform_factory(Credential, fields=["name", "description"]),
    "faculty-credentials": modelform_factory(FacultyCredential, fields=["faculty", "credential", "issued_by", "issued_on", "expires_on", "notes"], widgets={"issued_on": forms.DateInput(attrs={"type": "date"}), "expires_on": forms.DateInput(attrs={"type": "date"})}),
    "subject-credential-requirements": modelform_factory(SubjectCredentialRequirement, fields=["subject", "required_credential", "acceptable_equivalents", "notes"]),
    "faculty": modelform_factory(Faculty, fields=["user", "department", "employee_id", "full_name", "max_weekly_hours"]),
    "students": modelform_factory(Student, fields=["user", "section", "student_number", "full_name"]),
    "rooms": modelform_factory(Room, fields=["name", "room_type", "capacity", "is_active"]),
    "terms": modelform_factory(AcademicTerm, fields=["name", "school_year", "starts_on", "ends_on", "is_active"], widgets={"starts_on": forms.DateInput(attrs={"type": "date"}), "ends_on": forms.DateInput(attrs={"type": "date"})}),
    "assignments": modelform_factory(TeachingAssignment, fields=["term", "subject", "faculty", "section", "component", "meeting_index", "duration_minutes", "required_room_type_override"]),
    "availability": modelform_factory(Availability, fields=["faculty", "room", "day", "start_time", "end_time", "kind"], widgets={"start_time": forms.TimeInput(attrs={"type": "time"}), "end_time": forms.TimeInput(attrs={"type": "time"})}),
    "ga-settings": modelform_factory(GASettings, fields=["name", "population_size", "generations", "mutation_rate", "crossover_rate", "elitism"]),
    "schedules": modelform_factory(Schedule, fields=["term", "name", "status"]),
    "credential-overrides": modelform_factory(CredentialOverride, fields=["assignment", "subject", "faculty", "admin_user", "reason", "missing_credentials"]),
}


class TeachingAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeachingAssignment
        fields = ["term", "subject", "faculty", "section", "component", "meeting_index", "duration_minutes", "required_room_type_override"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("component", "meeting_index", "duration_minutes", "required_room_type_override"):
            self.fields[name].required = False

    def clean_component(self):
        return self.cleaned_data.get("component") or TeachingAssignment.Component.GENERAL

    def clean_meeting_index(self):
        return self.cleaned_data.get("meeting_index") or 1

    def clean_duration_minutes(self):
        return self.cleaned_data.get("duration_minutes") or 0


MODEL_FORMS["assignments"] = TeachingAssignmentForm


class ScheduleGenerationForm(forms.Form):
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all())
    settings = forms.ModelChoiceField(queryset=GASettings.objects.all())
    name = forms.CharField(max_length=120, initial="Generated Schedule")


class ScheduleEntryForm(forms.ModelForm):
    class Meta:
        model = ScheduleEntry
        fields = ["assignment", "room", "day", "start_time", "end_time"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class ScheduleSearchForm(forms.Form):
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all(), required=False)
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False)
    program = forms.ModelChoiceField(queryset=Program.objects.all(), required=False)
    year_level = forms.ModelChoiceField(queryset=YearLevel.objects.all(), required=False)
    section = forms.ModelChoiceField(queryset=Section.objects.all(), required=False)
    subject = forms.ModelChoiceField(queryset=Subject.objects.all(), required=False)


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
