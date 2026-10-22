import hashlib
import json

from django.forms.models import model_to_dict


def object_signature(instance):
    if instance is None:
        return ""
    values = model_to_dict(instance)
    if instance._meta.model_name == "assignment" and instance.pk:
        values["meetings"] = list(instance.meetings.order_by("pk").values(
            "id", "meeting_index", "component", "duration_minutes", "required_room_type_override"))
    normalized = {key: normalize_value(value) for key, value in sorted(values.items())}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_value(value):
    if isinstance(value, (list, tuple, set)):
        return [normalize_value(item) for item in value]
    if hasattr(value, "pk"):
        return str(value.pk)
    return str(value) if value is not None else ""


def safe_draft_payload(form_class, payload):
    fields = form_class.base_fields
    cleaned = {}
    for name, value in payload.items():
        if name not in fields:
            continue
        field = fields[name]
        values = value if isinstance(value, list) else [value]
        max_length = getattr(field, "max_length", None)
        normalized = []
        for item in values:
            text = str(item)
            if max_length and len(text) > max_length:
                text = text[:max_length]
            normalized.append(text)
        cleaned[name] = normalized if isinstance(value, list) else normalized[0]
    return cleaned


def safe_assignment_draft_payload(payload):
    """Keep only the existing meeting form fields, with bounded form counts."""
    from schedules.forms import AssignmentForm, AssignmentMeetingForm
    cleaned = safe_draft_payload(AssignmentForm, payload)
    try:
        total = min(max(int(payload.get("meetings-TOTAL_FORMS", 0)), 0), 1000)
        initial = min(max(int(payload.get("meetings-INITIAL_FORMS", 0)), 0), total)
    except (TypeError, ValueError):
        return cleaned
    if "meetings-TOTAL_FORMS" not in payload:
        return cleaned
    cleaned.update({"meetings-TOTAL_FORMS": str(total), "meetings-INITIAL_FORMS": str(initial),
                    "meetings-MIN_NUM_FORMS": "1", "meetings-MAX_NUM_FORMS": "1000"})
    for index in range(total):
        for field in [*AssignmentMeetingForm.base_fields, "id", "DELETE"]:
            key = f"meetings-{index}-{field}"
            value = payload.get(key, "")
            if isinstance(value, (str, int)):
                cleaned[key] = str(value)[:160]
    return cleaned
