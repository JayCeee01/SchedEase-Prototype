import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    FACULTY = "FACULTY", "Faculty"
    STUDENT = "STUDENT", "Student"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"


class RoomKind(models.TextChoices):
    LECTURE = "LECTURE", "Lecture Room"
    COMPUTER_LAB = "COMPUTER_LAB", "Computer Laboratory"
    SCIENCE_LAB = "SCIENCE_LAB", "Science Laboratory"
    GYM = "GYM", "Gym"
    SPECIAL = "SPECIAL", "Specialized Room"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Department(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Program(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class YearLevel(models.Model):
    level = models.PositiveSmallIntegerField(unique=True)
    label = models.CharField(max_length=40)

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.label


class AcademicTerm(models.Model):
    name = models.CharField(max_length=80)
    school_year = models.CharField(max_length=20)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-starts_on"]
        constraints = [models.UniqueConstraint(fields=["name", "school_year"], name="unique_term")]

    def __str__(self):
        return f"{self.name} {self.school_year}"

    def clean(self):
        if self.starts_on >= self.ends_on:
            raise ValidationError("Academic term end date must be after its start date.")


class Section(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    year_level = models.ForeignKey(YearLevel, on_delete=models.PROTECT)
    name = models.CharField(max_length=30)
    size = models.PositiveIntegerField(default=30)
    adviser = models.ForeignKey("Faculty", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["program__code", "year_level__level", "name"]
        constraints = [models.UniqueConstraint(fields=["program", "year_level", "name"], name="unique_section")]

    @property
    def section_code(self):
        return self.name

    @property
    def display_name(self):
        return f"{self.program.code.upper()} {self.year_level.level}-{self.name.upper()}"

    def clean(self):
        super().clean()
        value = re.sub(r"\s+", " ", (self.name or "").strip().upper())
        if self.program_id and self.year_level_id:
            full_name = re.fullmatch(
                rf"{re.escape(self.program.code)}\s+{self.year_level.level}-([A-Z0-9][A-Z0-9_-]*)",
                value,
                flags=re.IGNORECASE,
            )
            if full_name:
                value = full_name.group(1).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", value):
            raise ValidationError({"name": "Enter only the section code, such as 201, 202, or A."})
        self.name = value

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name


class Faculty(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    employee_id = models.CharField(max_length=40, unique=True)
    full_name = models.CharField(max_length=160)
    max_weekly_hours = models.PositiveSmallIntegerField(default=24)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Credential(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FacultyCredential(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="credentials")
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE)
    issued_by = models.CharField(max_length=160, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["faculty__full_name", "credential__name"]
        constraints = [models.UniqueConstraint(fields=["faculty", "credential"], name="unique_faculty_credential")]

    def __str__(self):
        return f"{self.faculty} - {self.credential}"


class Student(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    student_number = models.CharField(max_length=40, unique=True)
    full_name = models.CharField(max_length=160)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Room(models.Model):
    name = models.CharField(max_length=80, unique=True)
    room_type = models.CharField(max_length=30, choices=RoomKind.choices)
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_room_type_display()})"


class Subject(models.Model):
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=180)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    units = models.DecimalField(max_digits=4, decimal_places=1, default=3)
    lecture_hours = models.PositiveSmallIntegerField(default=3)
    lab_hours = models.PositiveSmallIntegerField(default=0)
    required_room_type = models.CharField(max_length=30, choices=RoomKind.choices, default=RoomKind.LECTURE)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class SubjectCredentialRequirement(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="credential_requirements")
    required_credential = models.ForeignKey(Credential, on_delete=models.PROTECT, related_name="subject_requirements")
    acceptable_equivalents = models.ManyToManyField(Credential, blank=True, related_name="equivalent_subject_requirements")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["subject__code", "required_credential__name"]
        constraints = [models.UniqueConstraint(fields=["subject", "required_credential"], name="unique_subject_credential_requirement")]

    def __str__(self):
        return f"{self.subject.code} requires {self.required_credential.name}"


class TeachingAssignment(models.Model):
    class Component(models.TextChoices):
        GENERAL = "GENERAL", "General"
        LECTURE = "LECTURE", "Lecture"
        LABORATORY = "LABORATORY", "Laboratory"

    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    component = models.CharField(max_length=20, choices=Component.choices, default=Component.GENERAL)
    meeting_index = models.PositiveSmallIntegerField(default=1)
    duration_minutes = models.PositiveSmallIntegerField(default=0, help_text="Per-meeting duration; zero uses the subject hours.")
    required_room_type_override = models.CharField(max_length=30, choices=RoomKind.choices, blank=True)
    source_key = models.CharField(max_length=160, blank=True, db_index=True)
    source_sheet = models.CharField(max_length=120, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["section", "subject__code"]
        constraints = [models.UniqueConstraint(fields=["term", "subject", "section", "component", "meeting_index"], name="unique_assignment_meeting")]

    @property
    def required_hours(self):
        return self.required_duration_minutes / 60

    @property
    def required_duration_minutes(self):
        if self.duration_minutes:
            return self.duration_minutes
        return int(self.subject.lecture_hours + self.subject.lab_hours) * 60

    @property
    def effective_room_type(self):
        return self.required_room_type_override or self.subject.required_room_type

    def __str__(self):
        return f"{self.section} {self.subject.code}"

    def clean(self):
        if self.required_duration_minutes <= 0:
            raise ValidationError("Teaching assignment must require a positive class duration.")


class CredentialOverride(models.Model):
    assignment = models.ForeignKey(TeachingAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="credential_overrides")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT)
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    missing_credentials = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Override: {self.faculty} for {self.subject}"


class AvailabilityKind(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    PREFERRED = "PREFERRED", "Preferred"
    UNAVAILABLE = "UNAVAILABLE", "Unavailable"


class Availability(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True)
    day = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    kind = models.CharField(max_length=20, choices=AvailabilityKind.choices, default=AvailabilityKind.AVAILABLE)

    class Meta:
        ordering = ["day", "start_time"]
        constraints = [
            models.CheckConstraint(
                check=(Q(faculty__isnull=False, room__isnull=True) | Q(faculty__isnull=True, room__isnull=False)),
                name="availability_exactly_one_owner",
            )
        ]

    def clean(self):
        if bool(self.faculty) == bool(self.room):
            raise ValidationError("Availability must belong to exactly one faculty member or room.")
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be earlier than end time.")


class GASettings(models.Model):
    name = models.CharField(max_length=80, default="Default")
    population_size = models.PositiveIntegerField(default=80)
    generations = models.PositiveIntegerField(default=120)
    mutation_rate = models.FloatField(default=0.08)
    crossover_rate = models.FloatField(default=0.85)
    elitism = models.PositiveIntegerField(default=4)

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if not 0 <= self.mutation_rate <= 1:
            errors["mutation_rate"] = "Mutation rate must be between 0 and 1."
        if not 0 <= self.crossover_rate <= 1:
            errors["crossover_rate"] = "Crossover rate must be between 0 and 1."
        if self.elitism >= self.population_size:
            errors["elitism"] = "Elitism must be smaller than the population size."
        if errors:
            raise ValidationError(errors)


class ScheduleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"
    PUBLISHED = "PUBLISHED", "Published"


class Schedule(models.Model):
    class Origin(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        IMPORTED = "IMPORTED", "Imported Original"
        GENERATED = "GENERATED", "SchedEase Generated"

    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.DRAFT)
    fitness_score = models.FloatField(default=0)
    generated_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return self.name


class ScheduleEntry(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="entries")
    assignment = models.ForeignKey(TeachingAssignment, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, on_delete=models.PROTECT)
    day = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["day", "start_time", "room__name"]
        constraints = [models.UniqueConstraint(fields=["schedule", "assignment"], name="unique_schedule_assignment")]

    def clean(self):
        from .services.conflicts import validate_entry

        validate_entry(self)

    def __str__(self):
        return f"{self.assignment} {self.get_day_display()} {self.start_time}-{self.end_time}"


class GenerationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        SUCCEEDED_WITH_ISSUES = "SUCCEEDED_WITH_ISSUES", "Succeeded with issues"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="generation_runs")
    ga_settings = models.ForeignKey(GASettings, on_delete=models.SET_NULL, null=True, related_name="generation_runs")
    schedule = models.ForeignKey(Schedule, on_delete=models.SET_NULL, null=True, blank=True, related_name="generation_runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="schedule_generation_runs")
    requested_name = models.CharField(max_length=120)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{str(self.id)[:8]} - {self.term}"


class GenerationIssue(models.Model):
    class Category(models.TextChoices):
        FACULTY_CONFLICT = "FACULTY_CONFLICT", "Faculty Conflict"
        ROOM_CONFLICT = "ROOM_CONFLICT", "Room Conflict"
        SECTION_CONFLICT = "SECTION_CONFLICT", "Section Conflict"
        FACULTY_UNAVAILABLE = "FACULTY_UNAVAILABLE", "Faculty Unavailable"
        ROOM_UNAVAILABLE = "ROOM_UNAVAILABLE", "Room Unavailable"
        ROOM_CAPACITY = "ROOM_CAPACITY", "Room Capacity"
        ROOM_TYPE = "ROOM_TYPE", "Room Type Requirement"
        FACULTY_CREDENTIAL = "FACULTY_CREDENTIAL", "Faculty Credential Requirement"
        FACULTY_WORKLOAD = "FACULTY_WORKLOAD", "Faculty Workload"
        INVALID_DURATION = "INVALID_DURATION", "Invalid Class Duration"
        NO_SLOT = "NO_SLOT", "No Available Time Slot"
        UNSCHEDULED = "UNSCHEDULED", "Unscheduled Class"
        INVALID_DATA = "INVALID_DATA", "Invalid Input/Data"
        GENERATION_FAILURE = "GENERATION_FAILURE", "Generation Failure"
        OTHER = "OTHER", "Other"

    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        REVIEWED = "REVIEWED", "Reviewed"
        RESOLVED = "RESOLVED", "Resolved"

    run = models.ForeignKey(GenerationRun, on_delete=models.CASCADE, related_name="issues")
    category = models.CharField(max_length=40, choices=Category.choices)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.ERROR)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    assignment = models.ForeignKey(TeachingAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="generation_issues")
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="generation_issues")
    short_description = models.CharField(max_length=240)
    reason = models.TextField()
    suggested_action = models.TextField()
    day = models.PositiveSmallIntegerField(choices=Weekday.choices, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"Issue {self.pk}: {self.get_category_display()}"


class FormDraft(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="form_drafts")
    resource = models.CharField(max_length=80)
    object_pk = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict)
    base_signature = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "resource", "object_pk"], name="unique_user_form_draft")
        ]

    @property
    def is_edit(self):
        return bool(self.object_pk)

    def __str__(self):
        target = f" record {self.object_pk}" if self.object_pk else " new record"
        return f"{self.user}: {self.resource}{target}"
