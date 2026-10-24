"""Versioned identifier comparison shared by validation, imports and SQLite."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction


def normalize_identity(value):
    return value.strip().casefold() if isinstance(value, str) else value


class NormalizedIdentity(models.Func):
    function = "schedease_identity_v1"
    arity = 1
    output_field = models.CharField()


RULES = {
    "Department": (("code",), ()), "Program": (("code",), ()),
    "Subject": (("code",), ()), "Faculty": (("employee_id",), ()),
    "Student": (("student_number",), ()), "Room": (("name",), ()),
    "Credential": (("name",), ()),
    "AcademicTerm": (("name", "school_year"), ()),
    "Section": (("name",), ("program_id", "year_level_id")),
}


def identity_query(model, keys, using=None):
    text_fields, _ = RULES.get(model.__name__, ((), ()))
    query = model.objects.using(using)
    for field, value in keys.items():
        if field in text_fields:
            alias = "identity_" + field
            query = query.alias(**{alias: NormalizedIdentity(field)}).filter(**{alias: normalize_identity(value)})
        else:
            query = query.filter(**{field: value})
    return query


class IdentityValidationMixin:
    def get_constraints(self):
        # These indexes are validated with field-specific errors below; retain
        # every other model constraint and all database enforcement.
        return [(model, [constraint for constraint in constraints
                         if not constraint.name.startswith("normalized_")])
                for model, constraints in super().get_constraints()]

    def validate_unique(self, exclude=None):
        self._validate_identity(exclude)
        return super().validate_unique(exclude=exclude)

    def validate_constraints(self, exclude=None):
        self._validate_identity(exclude)
        return super().validate_constraints(exclude=exclude)

    def _validate_identity(self, exclude=None):
        text_fields, scope = RULES[type(self).__name__]
        fields = (*text_fields, *scope)
        if any(getattr(self, field) in (None, "") or field in (exclude or ()) for field in fields):
            return
        query = identity_query(type(self), {field: getattr(self, field) for field in fields}, self._state.db)
        if not self._state.adding:
            query = query.exclude(pk=self.pk)
        if query.exists():
            field = text_fields[0]
            label = {"employee_id": "Employee ID", "student_number": "Student ID"}.get(field, self._meta.get_field(field).verbose_name.capitalize())
            suffix = " in this program and year level" if scope else " in this school year" if type(self).__name__ == "AcademicTerm" else ""
            raise ValidationError({field: f"{label} already exists{suffix}. Capitalization and surrounding spaces do not make it different."})


def identity_get_or_create(model, defaults=None, **keys):
    query = identity_query(model, keys)
    existing = query.first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            return model.objects.get_or_create(defaults=defaults, **keys)
    except IntegrityError:
        existing = query.first()
        if existing is None:
            raise
        return existing, False
