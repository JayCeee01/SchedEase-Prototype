from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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


class Section(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    year_level = models.ForeignKey(YearLevel, on_delete=models.PROTECT)
    name = models.CharField(max_length=30)
    size = models.PositiveIntegerField(default=30)
    adviser = models.ForeignKey("Faculty", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["program__code", "year_level__level", "name"]
        constraints = [models.UniqueConstraint(fields=["program", "year_level", "name"], name="unique_section")]

    def __str__(self):
        return f"{self.program.code}-{self.year_level.level}{self.name}"


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
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)

    class Meta:
        ordering = ["section", "subject__code"]
        constraints = [models.UniqueConstraint(fields=["term", "subject", "section"], name="unique_assignment")]

    @property
    def required_hours(self):
        return int(self.subject.lecture_hours + self.subject.lab_hours)

    def __str__(self):
        return f"{self.section} {self.subject.code}"


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

    def clean(self):
        if not self.faculty and not self.room:
            raise ValidationError("Availability must belong to a faculty member or a room.")
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


class ScheduleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"
    PUBLISHED = "PUBLISHED", "Published"


class Schedule(models.Model):
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.DRAFT)
    fitness_score = models.FloatField(default=0)
    generated_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

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

    class Meta:
        ordering = ["day", "start_time", "room__name"]

    def clean(self):
        from .services.conflicts import validate_entry

        validate_entry(self)

    def __str__(self):
        return f"{self.assignment} {self.get_day_display()} {self.start_time}-{self.end_time}"
