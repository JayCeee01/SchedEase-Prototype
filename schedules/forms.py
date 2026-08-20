import re

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
    Weekday,
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


class ScheduleEntryFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={
        "type": "search", "placeholder": "Section, subject, faculty, or room", "data-schedule-live-filter": "true",
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
