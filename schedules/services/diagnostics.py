"""Explicit, transient diagnostics shared by generation and validation."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    category: str
    message: str
    meeting_ids: tuple = ()
    assignment_ids: tuple = ()
    severity: str = 'ERROR'
    room_id: int | None = None
    details: dict = field(default_factory=dict)

    @classmethod
    def for_meetings(cls, category, message, meetings=(), **kwargs):
        return cls(category, message, tuple(sorted({m.pk for m in meetings if m.pk})),
                   tuple(sorted({m.assignment_id for m in meetings if m.assignment_id})), **kwargs)


class GenerationFailure(ValueError):
    def __init__(self, message, issues):
        super().__init__(message)
        self.issues = tuple(issues)


class ValidationMessages(list):
    def __init__(self, messages, issues):
        super().__init__(messages)
        self.issues = tuple(issues)
