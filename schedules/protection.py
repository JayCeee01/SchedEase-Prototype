"""H2 model feedback plus SQL predicates used by database integrity guards."""
from contextlib import contextmanager
from contextvars import ContextVar
from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models.deletion import ProtectedError

MESSAGE = "This record is used by a published or archived schedule and is locked. Keep it unchanged and use separate records for future scheduling."
FINAL = "('PUBLISHED', 'ARCHIVED')"
_archiving = ContextVar("schedease_archiving", default=False)
_term_sync = ContextVar("schedease_term_sync", default=None)
TERM_MESSAGE = "Academic terms must match across the schedule, assignment, and meeting. Remove draft entries before changing their term, or edit the parent assignment for unscheduled meetings."

# Only content and relationships are locked. Source metadata and timestamps remain editable.
FIELDS = {
    "academicterm": "name school_year starts_on ends_on education_level calendar_context",
    "department": "code name",
    "program": "department_id code name education_level",
    "yearlevel": "level label",
    "section": "program_id year_level_id name size cohort_id",
    "faculty": "department_id employee_id full_name max_weekly_hours",
    "room": "name room_type capacity is_active",
    "subject": "code title department_id units lecture_hours lab_hours required_room_type",
    "assignment": "term_id subject_id faculty_id section_id",
    "teachingassignment": "term_id subject_id faculty_id section_id component meeting_index duration_minutes required_room_type_override assignment_id",
    "schedule": "term_id name status fitness_score generated_at published_at archived_at replaced_by_id origin",
    "scheduleentry": "schedule_id assignment_id room_id day start_time end_time subject_override_id section_override_id faculty_override_id component_override",
    "scheduleentryaudit": "schedule_id entry_id user_id previous_values new_values created_at",
    "credentialoverride": "assignment_id subject_id faculty_id admin_user_id reason missing_credentials created_at",
}


def reference_sql(model, alias="OLD"):
    key = f"{alias}.id"
    if model == "academicterm":
        return (f"EXISTS (SELECT 1 FROM schedules_schedule p WHERE p.term_id={key} AND p.status IN {FINAL}) OR "
                "EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id "
                "JOIN schedules_teachingassignment a ON a.id=e.assignment_id "
                "LEFT JOIN schedules_assignment parent ON parent.id=a.assignment_id "
                f"WHERE p.status IN {FINAL} AND (a.term_id={key} OR parent.term_id={key}))")
    if model == "schedule":
        return f"{alias}.status IN {FINAL}"
    if model in ("scheduleentry", "scheduleentryaudit"):
        return f"EXISTS (SELECT 1 FROM schedules_schedule p WHERE p.id={alias}.schedule_id AND p.status IN {FINAL})"
    predicates = {
        "assignment": f"a.assignment_id={key}",
        "teachingassignment": f"a.id={key}",
        "subject": f"(a.subject_id={key} OR e.subject_override_id={key})",
        "faculty": f"(a.faculty_id={key} OR e.faculty_override_id={key})",
        "section": f"(a.section_id={key} OR e.section_override_id={key})",
        "room": f"e.room_id={key}",
        "program": f"EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND s.program_id={key})",
        "yearlevel": f"EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND s.year_level_id={key})",
        "department": f"(EXISTS (SELECT 1 FROM schedules_subject c WHERE c.id IN (a.subject_id, e.subject_override_id) AND c.department_id={key}) OR EXISTS (SELECT 1 FROM schedules_faculty f WHERE f.id IN (a.faculty_id, e.faculty_override_id) AND f.department_id={key}) OR EXISTS (SELECT 1 FROM schedules_section s JOIN schedules_program pr ON pr.id=s.program_id WHERE s.id IN (a.section_id, e.section_override_id) AND pr.department_id={key}))",
        "credentialoverride": f"a.id={alias}.assignment_id",
    }
    return ("EXISTS (SELECT 1 FROM schedules_scheduleentry e "
            "JOIN schedules_schedule p ON p.id=e.schedule_id "
            "JOIN schedules_teachingassignment a ON a.id=e.assignment_id "
            f"WHERE p.status IN {FINAL} AND ({predicates[model]}))")


def protected(instance, using=None):
    name = instance._meta.model_name
    if name not in FIELDS or not instance.pk:
        return False
    connection = connections[using or instance._state.db or "default"]
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT 1 FROM "{instance._meta.db_table}" target WHERE target.id=%s AND ({reference_sql(name, "target")})', [instance.pk])
        return cursor.fetchone() is not None


def check_changes(instance, update_fields=None, using=None):
    name = instance._meta.model_name
    if name not in FIELDS:
        return
    using = using or instance._state.db or "default"
    previous = type(instance)._base_manager.using(using).filter(pk=instance.pk).first() if instance.pk else None
    columns = {field.column: field for field in instance._meta.concrete_fields}
    changed = {column for column in FIELDS[name].split()
               if (update_fields is None or columns[column].name in update_fields or columns[column].attname in update_fields)
               and (previous is None or getattr(instance, columns[column].attname) != getattr(previous, columns[column].attname))}
    check_term_relationships(instance, previous, changed, using)
    if previous and changed and protected(previous, using):
        lifecycle = {"status", "archived_at", "replaced_by_id"}
        if not (name == "schedule" and _archiving.get() and previous.status == "PUBLISHED"
                and instance.status == "ARCHIVED" and changed <= lifecycle):
            raise ValidationError(MESSAGE)
    if name in ("teachingassignment", "credentialoverride") and (previous is None or "assignment_id" in changed):
        from .models import Assignment, TeachingAssignment
        owner_model = Assignment if name == "teachingassignment" else TeachingAssignment
        owner = owner_model.objects.using(using).filter(pk=instance.assignment_id).first()
        if owner and protected(owner, using):
            raise ValidationError(MESSAGE)
    if name in ("scheduleentry", "scheduleentryaudit") and (previous is None or "schedule_id" in changed):
        from .models import Schedule
        if Schedule.objects.using(using).filter(pk=instance.schedule_id, status__in=["PUBLISHED", "ARCHIVED"]).exists():
            raise ValidationError(MESSAGE)


def check_term_relationships(instance, previous, changed, using):
    from .models import Schedule, ScheduleEntry, TeachingAssignment
    name = instance._meta.model_name
    invalid = False
    if name == "schedule" and previous and "term_id" in changed:
        invalid = ScheduleEntry.objects.using(using).filter(schedule_id=instance.pk).exclude(assignment__term_id=instance.term_id).exists()
    elif name == "scheduleentry" and (previous is None or changed & {"schedule_id", "assignment_id"}):
        term = Schedule.objects.using(using).filter(pk=instance.schedule_id).values_list("term_id", flat=True).first()
        invalid = TeachingAssignment.objects.using(using).filter(pk=instance.assignment_id).exclude(term_id=term).exists()
    elif name == "teachingassignment" and (previous is None or changed & {"term_id", "assignment_id"}):
        # New inline meeting forms inherit the term in TeachingAssignment.save().
        invalid = bool(instance.assignment_id and instance.term_id is not None
                       and instance.assignment.term_id != instance.term_id)
        if previous:
            invalid |= ScheduleEntry.objects.using(using).filter(assignment_id=instance.pk).exclude(schedule__term_id=instance.term_id).exists()
    elif name == "assignment" and previous and "term_id" in changed:
        invalid = ScheduleEntry.objects.using(using).filter(assignment__assignment_id=instance.pk).exclude(schedule__term_id=instance.term_id).exists()
    if invalid:
        raise ValidationError(TERM_MESSAGE)


@contextmanager
def assignment_term_sync(parent_id, term_id):
    """Only the existing atomic parent-save workflow may synchronize child terms."""
    token = _term_sync.set((parent_id, term_id))
    try:
        yield
    finally:
        _term_sync.reset(token)


class ProtectedContentMixin:
    def clean(self):
        super().clean()
        check_changes(self)


def before_save(sender, instance, using, update_fields=None, **kwargs):
    check_changes(instance, update_fields, using)


def before_delete(sender, instance, using, **kwargs):
    if protected(instance, using):
        raise ProtectedError(MESSAGE, [instance])


def register_connection(connection, **kwargs):
    if connection.vendor == "sqlite" and connection.connection is not None:
        connection.connection.create_function("schedease_archiving", 0, lambda: int(_archiving.get()))
        connection.connection.create_function("schedease_term_sync", 2, lambda parent, term: int(_term_sync.get() == (parent, term)))


@contextmanager
def archive_transition():
    """Internal publication-service scope; permits metadata-only PUBLISHED -> ARCHIVED."""
    token = _archiving.set(True)
    try:
        yield
    finally:
        _archiving.reset(token)
