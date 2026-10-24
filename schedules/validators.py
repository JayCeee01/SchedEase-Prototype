"""Reusable academic identifier validation."""
from django.core.validators import RegexValidator

validate_student_id = RegexValidator(
    regex=r"\A[0-9]+\Z",
    message="Student ID must contain numbers only (0-9), without spaces.",
    code="invalid_student_id",
)
