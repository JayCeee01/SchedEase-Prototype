"""Atomic manual entry/approval/audit saves with SQLite-safe optimistic locking."""
from contextlib import contextmanager
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from schedules.models import CredentialOverride, Profile, Role, Schedule, ScheduleEntry, ScheduleEntryAudit, ScheduleStatus
from .credentials import faculty_qualification, valid_credential_override, missing_credential_message
from .form_drafts import object_signature

SALT = "schedules.manual-entry.v1"
STALE = "This schedule or meeting changed while you were editing. Reload the form, review the latest information, and try again."
FIELDS = ("assignment_id", "subject_override_id", "section_override_id", "faculty_override_id",
          "component_override", "room_id", "day", "start_time", "end_time")


def entry_signature(entry):
    return [object_signature(entry), entry.updated_at.isoformat()] if entry and entry.pk else None


def revision_token(schedule, user, entry=None):
    return signing.dumps({"schedule": schedule.pk, "user": user.pk, "entry": entry.pk if entry else None,
                          "term": schedule.term_id, "status": schedule.status,
                          "version": schedule.updated_at.isoformat(), "entry_version": entry_signature(entry)}, salt=SALT)


def values(entry):
    return {field: str(getattr(entry, field)) for field in FIELDS}


def authorized_administrator(actor):
    current_user = get_user_model().objects.get(pk=actor.pk)
    if not current_user.is_active or not (current_user.is_superuser or Profile.objects.filter(user=current_user, role=Role.ADMIN).exists()):
        raise ValidationError("Only an authorized administrator can save schedule changes.")
    return current_user


@contextmanager
def manual_edit_transaction(*, schedule_id, entry_id, actor, revision, draft_only=False):
    try:
        baseline = signing.loads(revision, salt=SALT, max_age=86400)
        if (baseline["schedule"], baseline["entry"], baseline["user"]) != (schedule_id, entry_id, actor.pk):
            raise ValidationError(STALE)
    except (signing.BadSignature, TypeError, KeyError):
        raise ValidationError("The edit form is missing or expired. Reload it before saving.")

    with transaction.atomic():
        # First database operation is a conditional write. On SQLite this obtains
        # the database write lock before reading conflicts/approvals/audit history.
        # A failed operation rolls this provisional revision update back too.
        candidates = Schedule.objects.filter(pk=schedule_id, updated_at=baseline["version"],
                  term_id=baseline["term"], status=baseline["status"]).exclude(
                  status__in=[ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED])
        if draft_only:
            candidates = candidates.filter(status=ScheduleStatus.DRAFT)
        claimed = candidates.update(updated_at=timezone.now())
        if claimed != 1:
            raise ValidationError(STALE)
        current_user = authorized_administrator(actor)
        schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
        if schedule.status in (ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED):
            raise ValidationError("Published and archived schedules are locked.")
        if entry_id:
            entry = ScheduleEntry.objects.select_for_update().filter(pk=entry_id, schedule=schedule).first()
            if entry is None or entry_signature(entry) != baseline["entry_version"]:
                raise ValidationError(STALE)
            previous = values(entry)
        else:
            entry = ScheduleEntry(schedule=schedule)
            previous = {}
        yield schedule, entry, previous, current_user


def save_manual_entry(*, schedule_id, entry_id, actor, revision, proposed, confirmed=False, reason=""):
    with manual_edit_transaction(schedule_id=schedule_id, entry_id=entry_id, actor=actor, revision=revision) as (schedule, entry, previous, current_user):
        for field in FIELDS:
            setattr(entry, field, proposed[field])
        entry.schedule = schedule
        qualified = faculty_qualification(entry.effective_faculty, entry.effective_subject, schedule.term)["qualified"]
        covered = valid_credential_override(entry.assignment, entry.effective_faculty, entry.effective_subject)
        if not qualified and not covered:
            if not confirmed or not reason.strip():
                raise ValidationError("Administrator confirmation and a reason are required for this credential override.")
            # Provisional approval is needed by full_clean; never committed alone.
            CredentialOverride.objects.create(assignment=entry.assignment, subject=entry.effective_subject,
                faculty=entry.effective_faculty, admin_user=current_user, reason=reason.strip(),
                missing_credentials=missing_credential_message(entry.effective_faculty, entry.effective_subject, schedule.term))
        entry.full_clean()
        entry.save()
        current = values(entry)
        if previous != current:
            ScheduleEntryAudit.objects.create(schedule=schedule, entry=entry, user=current_user,
                                               previous_values=previous, new_values=current)
        return entry


def remove_manual_entry(*, schedule_id, entry_id, actor, revision, confirmed=False):
    if not confirmed:
        raise ValidationError("Confirm removal of this meeting before continuing.")
    with manual_edit_transaction(schedule_id=schedule_id, entry_id=entry_id, actor=actor,
                                 revision=revision, draft_only=True) as (schedule, entry, previous, current_user):
        if not entry.pk:
            raise ValidationError("Choose a scheduled meeting to remove.")
        previous["entry_id"] = entry.pk
        entry.delete()
        ScheduleEntryAudit.objects.create(schedule=schedule, entry=None, user=current_user,
            previous_values=previous, new_values={"action": "remove_meeting"})


def copy_to_draft(*, source_id, actor):
    source = Schedule.objects.filter(pk=source_id, status__in=[ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED]).first()
    if source is None:
        raise ValidationError("Only published or archived schedules can be copied to a draft.")
    with transaction.atomic():
        # This first write locks SQLite before reading entries. The source itself
        # is never written, including its revision and historical timestamps.
        draft = Schedule.objects.create(term_id=source.term_id, name=(source.name + " - Draft")[:120],
                                         status=ScheduleStatus.DRAFT, origin=Schedule.Origin.MANUAL)
        current_user = authorized_administrator(actor)
        source = Schedule.objects.select_for_update().get(pk=source_id)
        if source.status not in (ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED) or source.term_id != draft.term_id:
            raise ValidationError("The source schedule changed. Reload it before copying.")
        originals = list(source.entries.order_by('pk'))
        copies = [ScheduleEntry(schedule=draft, **{field: getattr(entry, field) for field in FIELDS}) for entry in originals]
        # Keep even historical scheduling issues visible for correction in the
        # draft. Database guards still reject invalid term/foreign-key links.
        ScheduleEntry.objects.bulk_create(copies)
        ScheduleEntryAudit.objects.create(schedule=draft, entry=None, user=current_user,
            previous_values={}, new_values={"action": "copy_to_draft", "source_schedule_id": source.pk,
                "source_schedule_name": source.name, "entries": [
                    {"source_entry_id": original.pk, "draft_entry_id": copied.pk} for original, copied in zip(originals, copies)]})
        return draft
