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


class EducationLevel(models.TextChoices):
    TERTIARY = "TERTIARY", "Tertiary"
    SHS = "SHS", "Senior High School"


class AcademicIdentity(models.Model):
    """Validate identity records on ordinary saves, including admin and scripts."""
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumVersion(AcademicIdentity):
    class Verification(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", "Unverified"
        VERIFIED = "VERIFIED", "Verified"

    family = models.CharField(max_length=80, help_text="Curriculum family, not a subject list.")
    revision = models.CharField(max_length=80)
    education_level = models.CharField(max_length=8, choices=EducationLevel.choices, default=EducationLevel.SHS)
    reference_title = models.CharField(max_length=200, blank=True)
    reference_url = models.URLField(blank=True)
    reference_notes = models.TextField(blank=True)
    verification_status = models.CharField(max_length=10, choices=Verification.choices, default=Verification.UNVERIFIED)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["family", "revision"]
        constraints = [
            models.UniqueConstraint(NormalizedIdentity("family"), NormalizedIdentity("revision"), models.F("education_level"), name="unique_curriculum_version_identity"),
            models.CheckConstraint(condition=Q(is_active=False) | Q(verification_status="VERIFIED"), name="curriculum_activation_verified"),
            models.CheckConstraint(condition=Q(education_level__in=EducationLevel.values), name="curriculum_valid_level"),
        ]

    def clean(self):
        super().clean()
        if self.is_active and self.verification_status != self.Verification.VERIFIED:
            raise ValidationError({"is_active": "Verify the curriculum references before activation."})
        if self.verification_status == self.Verification.VERIFIED and not self.reference_title.strip():
            raise ValidationError({"reference_title": "Identify the reference used to verify this curriculum."})
        if self.pk and (self.cohort_set.exists() or self.academicpathway_set.exists() or self.curriculumsubjectrequirement_set.exists()):
            previous = type(self).objects.get(pk=self.pk)
            if any(getattr(previous, f) != getattr(self, f) for f in ("family", "revision", "education_level")):
                raise ValidationError("This curriculum identity is in use. Create a new version instead.")

    def __str__(self):
        return f"{self.family} / {self.revision}"


class AcademicPathway(AcademicIdentity):
    class Kind(models.TextChoices):
        TRACK = "TRACK", "Track"
        STRAND = "STRAND", "Strand"
        ELECTIVE_CLUSTER = "ELECTIVE_CLUSTER", "Elective cluster"

    curriculum_version = models.ForeignKey(CurriculumVersion, on_delete=models.PROTECT)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")

    class Meta:
        ordering = ["curriculum_version", "code"]
        constraints = [models.UniqueConstraint(models.F("curriculum_version"), NormalizedIdentity("code"), name="unique_pathway_identity")]

    def clean(self):
        super().clean()
        ancestor = self.parent if self.parent_id else None
        visited = {self.pk} if self.pk else set()
        while ancestor:
            if ancestor.pk in visited:
                raise ValidationError({"parent": "A pathway cannot be its own ancestor."})
            visited.add(ancestor.pk)
            if ancestor.curriculum_version_id != self.curriculum_version_id:
                raise ValidationError({"parent": "Choose a parent from the same curriculum version."})
            ancestor = ancestor.parent
        if self.pk and (self.cohort_set.exists() or self.children.exists() or self.curriculumsubjectrequirement_set.exists()):
            previous = type(self).objects.get(pk=self.pk)
            if any(getattr(previous, f) != getattr(self, f) for f in ("curriculum_version_id", "code", "kind", "parent_id")):
                raise ValidationError("This pathway identity is in use. Create a separate pathway instead.")

    def __str__(self):
        return f"{self.code} ({self.curriculum_version})"


class Cohort(AcademicIdentity):
    class Implementation(models.TextChoices):
        UNCONFIRMED = "UNCONFIRMED", "Unconfirmed"
        PILOT = "PILOT", "Pilot"
        IMPLEMENTED = "IMPLEMENTED", "Implemented"

    school_year = models.CharField(max_length=20)
    grade_level = models.PositiveSmallIntegerField(choices=[(11, "Grade 11"), (12, "Grade 12")])
    curriculum_version = models.ForeignKey(CurriculumVersion, on_delete=models.PROTECT)
    implementation_status = models.CharField(max_length=12, choices=Implementation.choices, default=Implementation.UNCONFIRMED)
    pathway = models.ForeignKey(AcademicPathway, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["school_year", "grade_level"]
        constraints = [
            models.CheckConstraint(condition=Q(grade_level__in=[11, 12]), name="cohort_shs_grade"),
            models.UniqueConstraint(NormalizedIdentity("school_year"), models.F("grade_level"), models.F("curriculum_version"), models.F("pathway"), condition=Q(pathway__isnull=False), name="unique_cohort_pathway"),
            models.UniqueConstraint(NormalizedIdentity("school_year"), models.F("grade_level"), models.F("curriculum_version"), condition=Q(pathway__isnull=True), name="unique_cohort_without_pathway"),
        ]

    def clean(self):
        super().clean()
        if self.curriculum_version_id and self.curriculum_version.education_level != EducationLevel.SHS:
            raise ValidationError({"curriculum_version": "Choose a Senior High School curriculum."})
        if self.pathway_id and self.pathway.curriculum_version_id != self.curriculum_version_id:
            raise ValidationError({"pathway": "Choose a pathway from this curriculum version."})
        if self.pk and (self.section_set.exists() or self.subjectoffering_set.exists()):
            previous = type(self).objects.get(pk=self.pk)
            if any(getattr(previous, f) != getattr(self, f) for f in ("school_year", "grade_level", "curriculum_version_id", "pathway_id")):
                raise ValidationError("This cohort identity is in use. Create a separate cohort instead.")

    def __str__(self):
        return f"{self.school_year} / Grade {self.grade_level} / {self.pathway or self.curriculum_version}"


class CurriculumSubjectRequirement(AcademicIdentity):
    """Source requirements, deliberately separate from weekly tertiary hours."""
    curriculum_version = models.ForeignKey(CurriculumVersion, on_delete=models.PROTECT)
    subject = models.ForeignKey("Subject", on_delete=models.PROTECT)
    pathway = models.ForeignKey(AcademicPathway, on_delete=models.PROTECT, null=True, blank=True)
    grade_level = models.PositiveSmallIntegerField(choices=[(11, "Grade 11"), (12, "Grade 12")])
    academic_period = models.CharField(max_length=40, help_text="Period identifier within the curriculum, for example Semester 1. Not a calendar date.")
    classification = models.CharField(max_length=80, help_text="Use the classification stated by this curriculum version's source.")
    selection = models.CharField(max_length=16, choices=[("REQUIRED", "Required"), ("ELECTIVE", "Elective choice")], default="REQUIRED")
    quantity = models.DecimalField(max_digits=9, decimal_places=2)
    unit = models.CharField(max_length=8, choices=[("HOURS", "Hours"), ("MINUTES", "Minutes")])
    measurement_basis = models.CharField(max_length=10, choices=[("WEEK", "Per week"), ("PERIOD", "Total for academic period")])
    reference_title = models.CharField(max_length=200, blank=True)
    reference_url = models.URLField(blank=True)
    reference_locator = models.CharField(max_length=200, blank=True, help_text="Page, table, or curriculum-guide section.")
    reference_notes = models.TextField(blank=True)
    verification_status = models.CharField(max_length=10, choices=CurriculumVersion.Verification.choices, default="UNVERIFIED")
    is_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="curriculum_requirement_positive"),
            models.CheckConstraint(condition=Q(grade_level__in=[11, 12]), name="curriculum_requirement_grade"),
            models.CheckConstraint(condition=Q(is_active=False) | Q(verification_status="VERIFIED"), name="requirement_activation_verified"),
            models.UniqueConstraint(models.F("curriculum_version"), models.F("subject"), models.F("grade_level"), NormalizedIdentity("academic_period"), models.F("pathway"), condition=Q(pathway__isnull=False), name="unique_requirement_pathway"),
            models.UniqueConstraint(models.F("curriculum_version"), models.F("subject"), models.F("grade_level"), NormalizedIdentity("academic_period"), condition=Q(pathway__isnull=True), name="unique_requirement_common"),
        ]

    def clean(self):
        super().clean()
        if self.curriculum_version_id and self.curriculum_version.education_level != EducationLevel.SHS:
            raise ValidationError({"curriculum_version": "Choose an SHS curriculum version."})
        if self.pathway_id and self.pathway.curriculum_version_id != self.curriculum_version_id:
            raise ValidationError({"pathway": "Choose a pathway from this curriculum version."})
        if self.verification_status == "VERIFIED" and not self.reference_title.strip():
            raise ValidationError({"reference_title": "Identify the source used to verify this requirement."})
        if self.is_active and self.curriculum_version_id and not (self.curriculum_version.is_active and self.curriculum_version.verification_status == "VERIFIED"):
            raise ValidationError({"is_active": "The curriculum version must be verified and active first."})
        if self.pk and self.subjectoffering_set.exists():
            previous = type(self).objects.get(pk=self.pk)
            fields = ("curriculum_version_id", "subject_id", "pathway_id", "grade_level", "academic_period", "classification", "selection", "quantity", "unit", "measurement_basis")
            if any(getattr(previous, field) != getattr(self, field) for field in fields):
                raise ValidationError("This requirement is used by an offering. Create a separate requirement or curriculum revision instead.")

    @property
    def approved_for_configuration(self):
        # Read current approval state, including parent deactivation after approval.
        return bool(self.pk and type(self).objects.filter(pk=self.pk, is_active=True, verification_status="VERIFIED", curriculum_version__is_active=True, curriculum_version__verification_status="VERIFIED", curriculum_version__education_level="SHS").exists())

    def __str__(self):
        return f"{self.subject} / Grade {self.grade_level} / {self.academic_period}"


class SubjectOffering(AcademicIdentity):
    """Approved configuration identity only; not a schedulable assignment."""
    requirement = models.ForeignKey(CurriculumSubjectRequirement, on_delete=models.PROTECT)
    cohort = models.ForeignKey(Cohort, on_delete=models.PROTECT)
    academic_term = models.ForeignKey("AcademicTerm", on_delete=models.PROTECT)
    academic_period = models.CharField(max_length=40)
    is_approved = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["requirement", "cohort", "academic_term"], name="unique_subject_offering")]

    def clean(self):
        super().clean()
        if self.pk and DeliveryPlan.objects.filter(offering_id=self.pk).exists():
            previous = type(self).objects.get(pk=self.pk)
            if any(getattr(previous, field) != getattr(self, field) for field in ("requirement_id", "cohort_id", "academic_term_id", "academic_period")):
                raise ValidationError("This offering has a delivery plan. Create a separate offering or remove the draft plan before changing its identity.")
        if not (self.requirement_id and self.cohort_id and self.academic_term_id):
            return
        from .identity import normalize_identity
        requirement, cohort, term = self.requirement, self.cohort, self.academic_term
        if requirement.curriculum_version_id != cohort.curriculum_version_id or requirement.grade_level != cohort.grade_level:
            raise ValidationError({"cohort": "The cohort must match the requirement's curriculum version and grade."})
        if requirement.pathway_id and requirement.pathway_id != cohort.pathway_id:
            raise ValidationError({"cohort": "The cohort must match the requirement's pathway."})
        if normalize_identity(self.academic_period) != normalize_identity(requirement.academic_period):
            raise ValidationError({"academic_period": "Use the academic period specified by the requirement."})
        if term.education_level != EducationLevel.SHS or normalize_identity(term.school_year) != normalize_identity(cohort.school_year):
            raise ValidationError({"academic_term": "Choose an SHS term in the cohort's school year."})
        if self.is_approved and not requirement.approved_for_configuration:
            raise ValidationError({"is_approved": "Verify and activate the requirement and its curriculum before approving this offering."})

    @property
    def approved_for_configuration(self):
        if not self.pk:
            return False
        current = type(self).objects.select_related("requirement__curriculum_version", "cohort", "academic_term").get(pk=self.pk)
        if not current.is_approved:
            return False
        try:
            current.full_clean()
        except ValidationError:
            return False
        return True

    def __str__(self):
        return f"{self.requirement} / {self.cohort} / {self.academic_term}"


class DeliveryPlan(AcademicIdentity):
    """Institutional contact-time configuration; never a GA scheduling input."""
    offering = models.OneToOneField(SubjectOffering, on_delete=models.PROTECT)
    reference_title = models.CharField(max_length=200, blank=True)
    reference_notes = models.TextField(blank=True)
    approval_reference = models.CharField(max_length=200, blank=True, help_text="Institutional approval reference. Required before approval.")
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)

    @property
    def planned_minutes(self):
        return sum(item.duration_minutes * item.meeting_count for item in self.components.all()) if self.pk else 0

    def approval_errors(self):
        if not self.offering_id:
            return ["Choose a subject offering."]
        # Fetch current state so cached related objects cannot retain approval.
        offering = SubjectOffering.objects.select_related("requirement").get(pk=self.offering_id)
        errors = []
        if not offering.approved_for_configuration:
            errors.append("The offering and its curriculum requirement must be verified, active, consistent, and approved.")
        if not self.reference_title.strip() or not self.approval_reference.strip():
            errors.append("Record the delivery-plan source and institutional approval reference.")
        requirement = offering.requirement
        required = requirement.quantity * (60 if requirement.unit == "HOURS" else 1)
        if required != required.to_integral_value():
            errors.append("The source requirement cannot be represented in whole minutes. Clarify it before approval.")
        if not self.pk or not self.components.exists():
            errors.append("Add at least one instructional component before approval.")
        elif self.planned_minutes != required:
            basis = "per week" if requirement.measurement_basis == "WEEK" else "for the whole academic period"
            errors.append(f"Planned time must equal {required:g} minutes {basis}; currently {self.planned_minutes} minutes.")
        return errors

    def clean(self):
        super().clean()
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if self.components.exists() and previous.offering_id != self.offering_id:
                raise ValidationError({"offering": "Remove draft components before changing the offering."})
            if previous.is_approved and self.is_approved and any(getattr(previous, f) != getattr(self, f) for f in ("reference_title", "reference_notes", "approval_reference")):
                raise ValidationError("Return the plan to draft before changing approved details.")
        if self.is_approved:
            errors = self.approval_errors()
            if errors:
                raise ValidationError({"is_approved": errors})

    @property
    def effective_status(self):
        if not self.pk:
            return "Draft"
        current = type(self).objects.get(pk=self.pk)
        return "Draft" if not current.is_approved else "Approval blocked" if current.approval_errors() else "Approved configuration"

    def __str__(self):
        return f"Delivery plan: {self.offering}"


class DeliveryComponent(AcademicIdentity):
    plan = models.ForeignKey(DeliveryPlan, on_delete=models.CASCADE, related_name="components")
    position = models.PositiveSmallIntegerField(default=1)
    instruction = models.CharField(max_length=120, help_text="Explicit instructional component from the institutional plan; not necessarily lecture or laboratory.")
    duration_minutes = models.PositiveIntegerField(help_text="Minutes per meeting.")
    meeting_count = models.PositiveIntegerField(help_text="Meetings per week for a weekly requirement, or total meetings for a period-total requirement. No weeks are inferred.")

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "position"], name="unique_delivery_component_position"),
            models.CheckConstraint(condition=Q(position__gt=0) & Q(duration_minutes__gt=0) & Q(meeting_count__gt=0), name="delivery_component_positive"),
        ]

    def clean(self):
        super().clean()
        ids = [self.plan_id]
        if self.pk:
            ids += list(type(self).objects.filter(pk=self.pk).values_list("plan_id", flat=True))
        if DeliveryPlan.objects.filter(pk__in=ids, is_approved=True).exists():
            raise ValidationError("Return the delivery plan to draft before changing its components.")

    def delete(self, *args, **kwargs):
        self.clean()
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.instruction}: {self.meeting_count} x {self.duration_minutes} minutes"


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


class SHSAssignmentConfiguration(AcademicIdentity):
    assignment = models.OneToOneField("Assignment", on_delete=models.PROTECT, related_name="shs_configuration")
    delivery_plan = models.ForeignKey(DeliveryPlan, on_delete=models.PROTECT)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    calendar_reference = models.CharField(max_length=200, blank=True, help_text="Approval for teaching dates, recurrence and operating windows. Use dated meetings when holidays interrupt weekly recurrence.")
    combined_class_reference = models.CharField(max_length=200, blank=True, help_text="Institutional approval for additional participating sections.")
    is_confirmed = models.BooleanField(default=False, help_text="Confirms these operational inputs only; does not authorize SHS generation or approve a workload policy.")

    def clean(self):
        super().clean()
        from .services.shs_operations import configuration_errors
        if self.assignment_id and self.delivery_plan_id:
            errors = configuration_errors(self, complete=self.is_confirmed)
            if errors:
                raise ValidationError(errors)

    def __str__(self):
        return f"SHS inputs: {self.assignment}"


class SHSSectionParticipation(AcademicIdentity):
    configuration = models.ForeignKey(SHSAssignmentConfiguration, on_delete=models.CASCADE, related_name="additional_sections")
    section = models.ForeignKey("Section", on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["configuration", "section"], name="unique_shs_participating_section")]

    def clean(self):
        super().clean()
        if self.configuration_id and self.section_id:
            config = self.configuration
            if self.section_id == config.assignment.section_id:
                raise ValidationError({"section": "The primary assignment section already participates."})
            if self.section.cohort_id != config.delivery_plan.offering.cohort_id or self.section.program.education_level != EducationLevel.SHS:
                raise ValidationError({"section": "Choose an SHS section from the offering's cohort."})
            if not config.combined_class_reference.strip():
                raise ValidationError("Record institutional combined-class approval before adding sections.")

    def __str__(self):
        return str(self.section)


class SHSMeetingPattern(AcademicIdentity):
    configuration = models.ForeignKey(SHSAssignmentConfiguration, on_delete=models.CASCADE, related_name="patterns")
    component = models.ForeignKey(DeliveryComponent, on_delete=models.PROTECT)
    sequence = models.PositiveSmallIntegerField(default=1)
    recurrence = models.CharField(max_length=8, choices=[("WEEKLY", "Weekly throughout teaching dates"), ("DATED", "One explicitly dated meeting")])
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    meeting_date = models.DateField(null=True, blank=True)
    window_start = models.TimeField()
    window_end = models.TimeField()
    required_room_type = models.CharField(max_length=30, choices=RoomKind.choices)
    room = models.ForeignKey("Room", on_delete=models.PROTECT, help_text="Explicitly approved eligible room for this pattern; other specialized rooms are not assumed equivalent.")
    room_approval_reference = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["configuration", "component", "sequence"], name="unique_shs_meeting_pattern"),
            models.CheckConstraint(condition=Q(sequence__gt=0) & Q(weekday__lte=5), name="shs_pattern_sequence_day"),
            models.CheckConstraint(condition=Q(window_end__gt=models.F("window_start")), name="shs_pattern_window"),
            models.CheckConstraint(condition=Q(recurrence="WEEKLY",meeting_date__isnull=True) | Q(recurrence="DATED",meeting_date__isnull=False), name="shs_pattern_recurrence_date"),
        ]

    def clean(self):
        super().clean()
        from .services.shs_operations import pattern_errors
        if self.configuration_id and self.component_id and self.room_id:
            errors = pattern_errors(self)
            if errors:
                raise ValidationError(errors)

    def __str__(self):
        return f"{self.component.instruction} / {self.get_weekday_display()} / {self.get_recurrence_display()}"


class FacultyContactMinutePolicy(AcademicIdentity):
    """Explicit policy input; no institutional default or workload-unit conversion."""
    faculty = models.ForeignKey("Faculty", on_delete=models.PROTECT)
    accounting_period = models.CharField(max_length=20, choices=[("CALENDAR_WEEK", "Calendar week")])
    covered_levels = models.CharField(max_length=20, choices=[("SHS_AND_TERTIARY", "SHS and tertiary combined")])
    week_starts_on = models.PositiveSmallIntegerField(choices=[(0,"Monday")])
    starts_on = models.DateField()
    ends_on = models.DateField()
    maximum_contact_minutes = models.PositiveIntegerField()
    reference = models.CharField(max_length=240, blank=True)
    is_verified = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(maximum_contact_minutes__gt=0), name="contact_policy_positive_limit"),
            models.CheckConstraint(condition=Q(ends_on__gte=models.F("starts_on")), name="contact_policy_dates"),
            models.CheckConstraint(condition=Q(week_starts_on=0), name="contact_policy_week_start"),
            models.CheckConstraint(condition=Q(accounting_period="CALENDAR_WEEK",covered_levels="SHS_AND_TERTIARY"), name="contact_policy_supported_contract"),
            models.CheckConstraint(condition=Q(is_approved=False) | Q(is_verified=True), name="contact_policy_approval_verified"),
            models.CheckConstraint(condition=Q(is_active=False) | Q(is_verified=True,is_approved=True), name="contact_policy_active_approved"),
        ]

    def clean(self):
        super().clean()
        if (self.is_verified or self.is_approved or self.is_active) and not self.reference.strip():
            raise ValidationError({"reference": "Record the verified institutional approval reference. Synthetic approvals belong only in isolated tests."})
        if self.is_active and self.faculty_id and self.starts_on and self.ends_on:
            if type(self).objects.filter(faculty_id=self.faculty_id,is_active=True,
                    starts_on__lte=self.ends_on,ends_on__gte=self.starts_on).exclude(pk=self.pk).exists():
                raise ValidationError("An active contact-minute policy already overlaps these dates for this faculty member.")

    def __str__(self):
        return f"{self.faculty} / {self.starts_on} to {self.ends_on} / contact minutes"


class SHSMeetingBinding(AcademicIdentity):
    """Immutable operational snapshot for a shared TeachingAssignment."""
    meeting = models.OneToOneField("TeachingAssignment", on_delete=models.PROTECT, related_name="shs_binding")
    pattern = models.ForeignKey(SHSMeetingPattern, on_delete=models.PROTECT)
    data = models.JSONField()

    def clean(self):
        super().clean()
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(data=self.data, meeting_id=self.meeting_id, pattern_id=self.pattern_id).exists():
            raise ValidationError('SHS meeting snapshots cannot be edited; prepare a new operational configuration.')


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
    education_level = models.CharField(max_length=8, choices=EducationLevel.choices, default=EducationLevel.TERTIARY, db_default=EducationLevel.TERTIARY)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(NormalizedIdentity("code"), name="normalized_program_identity")]


    def __str__(self):
        return self.code

    def clean(self):
        super().clean()
        if self.pk and self.education_level != EducationLevel.SHS and self.section_set.filter(cohort__isnull=False).exists():
            raise ValidationError({"education_level": "Programs with SHS cohorts must remain Senior High School."})


class YearLevel(ProtectedContentMixin, models.Model):
    level = models.PositiveSmallIntegerField(unique=True)
    label = models.CharField(max_length=40)

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.label


class AcademicTerm(IdentityValidationMixin, ProtectedContentMixin, models.Model):
    education_level = models.CharField(max_length=8, choices=EducationLevel.choices, default=EducationLevel.TERTIARY, db_default=EducationLevel.TERTIARY)
    calendar_context = models.CharField(max_length=120, blank=True, default="", db_default="", help_text="Optional calendar label. Scheduling continues to use the existing start and end dates.")
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
    cohort = models.ForeignKey(Cohort, on_delete=models.PROTECT, null=True, blank=True)
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
        if self.cohort_id:
            if self.program_id and self.program.education_level != EducationLevel.SHS:
                raise ValidationError({"cohort": "Only an SHS program can use an SHS cohort."})
            if self.year_level_id and self.year_level.level != self.cohort.grade_level:
                raise ValidationError({"cohort": "The cohort grade must match the section year level."})
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
        return f"{self.code} â€” {self.title}"

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
        return f"{self.subject.code} â€” {self.subject.title} â€” {self.section} â€” {self.faculty}"

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
        return f"{self.subject.code} â€” {self.subject.title} â€” {self.section} â€” Meeting {self.meeting_index} ({self.get_component_display()})"

    def clean(self):
        super().clean()
        from .services.meetings import duration_errors
        errors = duration_errors(self.required_duration_minutes)
        from .services.room_compatibility import meeting_room_errors
        room_errors = meeting_room_errors(self)
        problems = {}
        if errors:
            problems["duration_minutes"] = errors
        if room_errors:
            problems["required_room_type_override"] = room_errors
        if problems:
            raise ValidationError(problems)

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
