"""Term-wide credential validity and explicitly scoped override checks."""


def faculty_qualification(faculty, subject, term=None):
    requirements = list(subject.credential_requirements.select_related("required_credential").prefetch_related("acceptable_equivalents"))
    if not requirements:
        return {"qualified": True, "missing": [], "matched": []}
    start = getattr(term, "starts_on", None)
    end = getattr(term, "ends_on", None)
    dates_known = bool(start and end and start < end)
    valid_names = set()
    for held in faculty.credentials.select_related("credential"):
        if (dates_known and held.issued_on and held.issued_on <= start
                and (held.expires_on is None or held.expires_on >= end)):
            valid_names.add(held.credential.name)
    missing, matched = [], []
    for requirement in requirements:
        accepted = [requirement.required_credential.name]
        accepted.extend(item.name for item in requirement.acceptable_equivalents.all())
        if any(name in valid_names for name in accepted):
            matched.append(requirement.required_credential.name)
        else:
            missing.append({"required": requirement.required_credential.name, "acceptable": accepted})
    return {"qualified": not missing, "missing": missing, "matched": matched}


def valid_credential_override(assignment, faculty, subject):
    if not assignment or not assignment.pk:
        return False
    return any(override.assignment_id == assignment.pk
               and override.faculty_id == faculty.pk and override.subject_id == subject.pk
               and override.admin_user_id and override.reason.strip() and override.missing_credentials.strip()
               for override in assignment.credential_overrides.all())


def teaching_eligibility(faculty, subject, term, assignment=None):
    result = faculty_qualification(faculty, subject, term)
    result["overridden"] = valid_credential_override(assignment, faculty, subject)
    result["eligible"] = result["qualified"] or result["overridden"]
    return result


def missing_credential_message(faculty, subject, term=None):
    result = faculty_qualification(faculty, subject, term)
    if result["qualified"]:
        return ""
    parts = []
    for item in result["missing"]:
        equivalents = [name for name in item["acceptable"] if name != item["required"]]
        parts.append(item["required"] + (f" (acceptable equivalents: {', '.join(equivalents)})" if equivalents else ""))
    return (f"{faculty} is missing required credential(s) valid for the full academic term for {subject}: {', '.join(parts)}. "
            "Check the term dates and credential issue/expiry dates, or request an administrator override with a reason. "
            "Issue dates must be on or before the term starts; expiry dates must be on or after it ends. "
            "A missing issue date cannot confirm eligibility; a blank expiry date means no expiry restriction.")
