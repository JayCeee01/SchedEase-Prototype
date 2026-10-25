"""Term-end eligibility (Option B) and explicitly scoped override checks.

A known issue date on/before term end qualifies if expiry is absent or on/after
term end. Missing or invalid term dates still fail closed.
"""


def faculty_qualification(faculty, subject, term=None):
    requirements = list(subject.credential_requirements.select_related("required_credential").prefetch_related("acceptable_equivalents"))
    if not requirements:
        return {"qualified": True, "missing": [], "matched": []}
    start = getattr(term, "starts_on", None)
    end = getattr(term, "ends_on", None)
    dates_known = bool(start and end and start < end)
    valid_names = set()
    held_records = list(faculty.credentials.select_related("credential"))
    for held in held_records:
        if (dates_known and held.issued_on and held.issued_on <= end
                and (held.expires_on is None or held.expires_on >= end)):
            valid_names.add(held.credential.name)
    missing, matched = [], []
    for requirement in requirements:
        accepted = [requirement.required_credential.name]
        accepted.extend(item.name for item in requirement.acceptable_equivalents.all())
        if any(name in valid_names for name in accepted):
            matched.append(requirement.required_credential.name)
        else:
            reasons = []
            matching = [held for held in held_records if held.credential.name in accepted]
            if not dates_known:
                reasons.append("The academic term needs valid start and end dates before credentials can be checked.")
            if not matching:
                reasons.append("No required or accepted equivalent credential is assigned to this faculty member.")
            for held in matching:
                name = held.credential.name
                if not held.issued_on:
                    reasons.append(f"{name}: the issue date is missing. Enter the actual issue date to check eligibility.")
                elif dates_known and held.issued_on > end:
                    reasons.append(f"{name}: issued on {held.issued_on:%Y-%m-%d}, after the term ends on {end:%Y-%m-%d}.")
                if dates_known and held.expires_on and held.expires_on < end:
                    reasons.append(f"{name}: expires on {held.expires_on:%Y-%m-%d}, before the term ends on {end:%Y-%m-%d}.")
            missing.append({"required": requirement.required_credential.name, "acceptable": accepted, "reasons": reasons})
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
    return (f"{faculty} does not meet the credential requirements for {subject}. " +
            " ".join(f"{item['required']}: " + " ".join(item["reasons"]) for item in result["missing"]) +
            " Credentials must be issued on or before the term ends and must not expire before that date. "
            "A blank expiry date means no expiry restriction. An authorized override requires a reason.")
