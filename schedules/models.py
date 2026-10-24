import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from .protection import ProtectedContentMixin
from .validators import validate_student_id
from .identity import IdentityValidationMixin, NormalizedIdentity


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


class Department(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("code"), name="normalized_department_identity")]


    def __str__(self):
        return self.code


class Program(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("code"), name="normalized_program_identity")]


    def __str__(self):
        return self.code


class YearLevel(ProtectedContentMixin, models.Model):
    level = models.PositiveSmallIntegerField(unique=True)
    label = models.CharField(max_length=40)

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.label


class AcademicTerm(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    name = models.CharField(max_length=80)
    school_year = models.CharField(max_length=20)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-starts_on"]
        constraints = [models.UniqueConstraint(fields=["name", "school_year"], name="unique_term")]
        constraints += [models.UniqueConstraint(NormalizedIdentity("name"), NormalizedIdentity("school_year"), name="normalized_academicterm_identity")]


    def __str__(self):
        return f"{self.name} {self.school_year}"

    def clean(self):
        super().clean()
        if self.starts_on >= self.ends_on:
            raise ValidationError("Academic term end date must be after its start date.")


class Section(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    year_level = models.ForeignKey(YearLevel, on_delete=models.PROTECT)
    name = models.CharField(max_length=30)
    size = models.PositiveIntegerField(default=30)
    adviser = models.ForeignKey("Faculty", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["program__code", "year_level__level", "name"]
        constraints = [models.UniqueConstraint(fields=["program", "year_level", "name"], name="unique_section")]
        constraints += [models.UniqueConstraint(NormalizedIdentity("name"), models.F("program"), models.F("year_level"), name="normalized_section_identity")]


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


class Faculty(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    employee_id = models.CharField(max_length=40, unique=True)
    full_name = models.CharField(max_length=160)
    max_weekly_hours = models.PositiveSmallIntegerField(default=24)

    class Meta:
        ordering = ["full_name"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("employee_id"), name="normalized_faculty_identity")]


    def __str__(self):
        return self.full_name


class Credential(IdentityValidationMixin, models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("name"), name="normalized_credential_identity")]


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


class Student(IdentityValidationMixin, models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    student_number = models.CharField(max_length=40, unique=True, validators=[validate_student_id])
    full_name = models.CharField(max_length=160)

    class Meta:
        ordering = ["full_name"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("student_number"), name="normalized_student_identity")]


    def __str__(self):
        return self.full_name


class Room(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    name = models.CharField(max_length=80, unique=True)
    room_type = models.CharField(max_length=30, choices=RoomKind.choices)
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("name"), name="normalized_room_identity")]


    def __str__(self):
        return f"{self.name} ({self.get_room_type_display()})"


class Subject(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=180)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    units = models.DecimalField(max_digits=4, decimal_places=1, default=3)
    lecture_hours = models.PositiveSmallIntegerField(default=3)
    lab_hours = models.PositiveSmallIntegerField(default=0)
    required_room_type = models.CharField(max_length=30, choices=RoomKind.choices, default=RoomKind.LECTURE)
    created_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("code"), name="normalized_subject_identity")]


    def __str__(self):
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        now = timezone.now()
        self.created_at = self.created_at or now
        self.updated_at = now
        return super().save(*args, **kwargs)


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


class WorkloadApproval(models.Model):
    """Append-only application audit; no editing or deletion endpoint."""
    administrator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    evidence = models.JSONField(default=dict)


class Assignment(ProtectedContentMixin, models.Model):
    SHARED_FIELDS = ("term", "subject", "faculty", "section")

    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section", "subject__code"]
        constraints = [models.UniqueConstraint(
            fields=["term", "subject", "section", "faculty"], name="unique_parent_assignment"
        )]

    def __str__(self):
        return f"{self.subject.code} — {self.subject.title} — {self.section} — {self.faculty}"

    def _shared_changes(self, previous, update_fields=None):
        return [field for field in self.SHARED_FIELDS
                if (update_fields is None or field in update_fields or field + "_id" in update_fields)
                and getattr(previous, field + "_id") != getattr(self, field + "_id")]

    def _check_schedule_references(self, changes):
        if changes and ScheduleEntry.objects.filter(assignment__assignment_id=self.pk).exists():
            raise ValidationError(
                "This assignment has meetings used by a schedule. Its term, course, section, and faculty "
                "cannot be changed here, including for draft schedules. Keep this assignment unchanged "
                "and use the schedule review workflow to plan a separate revision."
            )

    def clean(self):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous:
                changes = self._shared_changes(previous)
                self._check_schedule_references(changes)
                if changes:
                    for meeting in self.meetings.all():
                        meeting.assignment = self
                        for field in self.SHARED_FIELDS:
                            setattr(meeting, field, getattr(self, field))
                        try:
                            meeting.full_clean()
                        except ValidationError as exc:
                            raise ValidationError("Assignment was not saved. " + " ".join(exc.messages)) from exc
        super().clean()

    def save(self, *args, **kwargs):
        # Keep normal model/admin saves consistent as well as the assignment editor.
        from .protection import assignment_term_sync
        with transaction.atomic(), assignment_term_sync(self.pk, self.term_id):
            previous = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
            changes = self._shared_changes(previous, kwargs.get("update_fields")) if previous else []
            self._check_schedule_references(changes)
            result = super().save(*args, **kwargs)
            if changes:
                parent = type(self).objects.get(pk=self.pk)
                parent.full_clean()
                for meeting in self.meetings.select_for_update().all():
                    meeting.assignment = parent
                    for field in self.SHARED_FIELDS:
                        setattr(meeting, field, getattr(parent, field))
                    meeting.full_clean()
                    meeting.save(update_fields=list(self.SHARED_FIELDS))
            return result


class TeachingAssignment(ProtectedContentMixin, models.Model):
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
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="meetings", null=True, blank=True)

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
        subject = self.subject if self.subject_id else getattr(self.assignment, "subject", None)
        if subject is None:
            return 0
        hours = {self.Component.LECTURE: subject.lecture_hours, self.Component.LABORATORY: subject.lab_hours}
        return int(hours.get(self.component, subject.lecture_hours + subject.lab_hours)) * 60

    @property
    def effective_room_type(self):
        return self.required_room_type_override or self.subject.required_room_type

    def __str__(self):
        return f"{self.subject.code} — {self.subject.title} — {self.section} — Meeting {self.meeting_index} ({self.get_component_display()})"

    def clean(self):
        super().clean()
        from .services.meetings import duration_errors
        errors = duration_errors(self.required_duration_minutes)
        if errors:
            raise ValidationError({"duration_minutes": errors})

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.assignment_id and all((self.term_id, self.subject_id, self.faculty_id, self.section_id)):
            self.assignment, _ = Assignment.objects.get_or_create(
                term_id=self.term_id,
                subject_id=self.subject_id,
                faculty_id=self.faculty_id,
                section_id=self.section_id,
            )
        if self.assignment_id:
            self.term = self.assignment.term
            self.subject = self.assignment.subject
            self.faculty = self.assignment.faculty
            self.section = self.assignment.section
        return super().save(*args, **kwargs)


class CredentialOverride(ProtectedContentMixin, models.Model):
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
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True)
    day = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    kind = models.CharField(max_length=20, choices=AvailabilityKind.choices, default=AvailabilityKind.AVAILABLE)

    class Meta:
        ordering = ["day", "start_time"]
        constraints = [
            models.CheckConstraint(
                check=(Q(faculty__isnull=False, room__isnull=True, section__isnull=True)
                       | Q(faculty__isnull=True, room__isnull=False, section__isnull=True)
                       | Q(faculty__isnull=True, room__isnull=True, section__isnull=False)),
                name="availability_exactly_one_owner",
            )
        ]

    def __str__(self):
        owner = self.faculty if self.faculty_id else self.room if self.room_id else self.section if self.section_id else "No owner selected"
        start = self.start_time.strftime("%H:%M") if self.start_time else "--:--"
        end = self.end_time.strftime("%H:%M") if self.end_time else "--:--"
        return f"{owner} - {self.get_day_display()} {start}-{end} - {self.get_kind_display()}"

    def clean(self):
        if sum(bool(value) for value in (self.faculty_id, self.room_id, self.section_id)) != 1:
            raise ValidationError("Choose exactly one faculty member, room, or section.")
        if self.section_id and self.kind == AvailabilityKind.PREFERRED:
            raise ValidationError("Section availability must be Available or Unavailable.")
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
    ARCHIVED = "ARCHIVED", "Archived"


class Schedule(ProtectedContentMixin, models.Model):
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
    archived_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replaced_schedules")
    updated_at = models.DateTimeField(auto_now=True)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)

    class Meta:
        ordering = ["-generated_at"]
        constraints = [models.UniqueConstraint(
            fields=["term"], condition=Q(status=ScheduleStatus.PUBLISHED), name="one_published_schedule_per_term"
        )]

    def __str__(self):
        return self.name


class ScheduleSnapshot(models.Model):
    """Database-captured finalization record. No application writes are allowed."""
    schedule = models.OneToOneField(Schedule, on_delete=models.PROTECT, related_name="snapshot")
    schema_version = models.PositiveSmallIntegerField(default=1)
    captured_at = models.DateTimeField()
    reconstructed = models.BooleanField(default=False)
    data = models.JSONField()

    def save(self, *args, **kwargs):
        raise ValidationError("Historical snapshots are created by finalization and cannot be changed.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Historical snapshots cannot be deleted.")


class ScheduleEntry(ProtectedContentMixin, models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="entries")
    assignment = models.ForeignKey(TeachingAssignment, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, on_delete=models.PROTECT)
    day = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    subject_override = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True, related_name="schedule_entry_overrides")
    section_override = models.ForeignKey(Section, on_delete=models.PROTECT, null=True, blank=True, related_name="schedule_entry_overrides")
    faculty_override = models.ForeignKey(Faculty, on_delete=models.PROTECT, null=True, blank=True, related_name="schedule_entry_overrides")
    component_override = models.CharField(max_length=20, choices=TeachingAssignment.Component.choices, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["day", "start_time", "room__name"]
        constraints = [models.UniqueConstraint(fields=["schedule", "assignment"], name="unique_schedule_assignment")]

    def clean(self):
        from .services.conflicts import validate_entry

        errors = []
        for validate in (super().clean, lambda: validate_entry(self)):
            try:
                validate()
            except ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            raise ValidationError(errors)

    @property
    def effective_subject(self):
        return self.subject_override or self.assignment.subject

    @property
    def effective_section(self):
        return self.section_override or self.assignment.section

    @property
    def effective_faculty(self):
        return self.faculty_override or self.assignment.faculty

    @property
    def effective_component(self):
        return self.component_override or self.assignment.component

    @property
    def effective_component_display(self):
        return dict(TeachingAssignment.Component.choices).get(self.effective_component, self.effective_component)

    def __str__(self):
        return f"{self.assignment} {self.get_day_display()} {self.start_time}-{self.end_time}"


class ScheduleEntryAudit(ProtectedContentMixin, models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="edit_audits")
    entry = models.ForeignKey(ScheduleEntry, on_delete=models.SET_NULL, null=True, related_name="edit_audits")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    previous_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class GenerationLease(models.Model):
    """One shared generation owner per term; expired owners cannot save."""
    term = models.OneToOneField(AcademicTerm, on_delete=models.CASCADE, primary_key=True)
    owner = models.UUIDField(null=True, editable=False)
    expires_at = models.DateTimeField(null=True)


class GenerationRun(models.Model):
    reproducibility = models.JSONField(default=dict, blank=True)
    lease_owner = models.UUIDField(null=True, editable=False)
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
    details = models.JSONField(default=dict, blank=True)
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


class AcademicImport(models.Model):
    """Owner-bound, expiring review payload; never a schedule or timetable."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    preview_signature = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


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


class ScheduleConcern(models.Model):
    class Category(models.TextChoices):
        TIME = 'TIME', 'Conflicting class times'
        ROOM = 'ROOM', 'Room conflict or unavailable room'
        SUBJECT = 'SUBJECT', 'Incorrect or missing subject'
        ASSIGNMENT = 'ASSIGNMENT', 'Incorrect faculty or section'
        OTHER = 'OTHER', 'Other scheduling concern'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
        RESOLVED = 'RESOLVED', 'Resolved'
        REJECTED = 'REJECTED', 'Rejected'

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='schedule_concerns')
    reporter_role = models.CharField(max_length=10, choices=[(Role.STUDENT, 'Student'), (Role.FACULTY, 'Faculty')])
    schedule = models.ForeignKey(Schedule, null=True, on_delete=models.SET_NULL)
    entry = models.ForeignKey(ScheduleEntry, null=True, blank=True, on_delete=models.SET_NULL)
    reference = models.JSONField(default=dict, editable=False)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(max_length=3000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    response = models.TextField(max_length=3000, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='reviewed_schedule_concerns')
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-submitted_at', '-pk']

    def clean(self):
        if not 10 <= len(self.description.strip()) <= 3000:
            raise ValidationError({'description': 'Enter between 10 and 3000 characters.'})
        if len(self.response) > 3000:
            raise ValidationError({'response': 'Use no more than 3000 characters.'})


class ConcernReview(models.Model):
    concern = models.ForeignKey(ScheduleConcern, on_delete=models.PROTECT, related_name='reviews')
    administrator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    previous_status = models.CharField(max_length=20, choices=ScheduleConcern.Status.choices)
    status = models.CharField(max_length=20, choices=ScheduleConcern.Status.choices)
    previous_response = models.TextField(blank=True)
    response = models.TextField(blank=True)

    class Meta:
        ordering = ['-reviewed_at', '-pk']
