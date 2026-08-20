import hashlib
import json

from django.forms.models import model_to_dict


def object_signature(instance):
    if instance is None:
        return ""
    values = model_to_dict(instance)
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
