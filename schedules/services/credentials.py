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
            missing.append({"required": requirement.required_credential.name, "acceptable": accepted, "reasons": reasons,
                "definition": {"id": requirement.pk, "subject_id": subject.pk,
                    "required_credential_id": requirement.required_credential_id,
                    "equivalent_ids": sorted(item.pk for item in requirement.acceptable_equivalents.all())}})
    return {"qualified": not missing, "missing": missing, "matched": matched}


def valid_credential_override(assignment, faculty, subject, *, term=None, qualification=None):
    if not assignment or not assignment.pk:
        return False
    overrides = [o for o in assignment.credential_overrides.all()
                 if o.faculty_id == faculty.pk and o.subject_id == subject.pk
                 and o.admin_user_id and o.reason.strip() and o.missing_credentials.strip()]
    if not overrides:
        return False
    from schedules.models import CredentialApprovalEvidence
    from .credential_approval import scope_context
    term = term or assignment.term
    if not term.starts_on or not term.ends_on or term.starts_on >= term.ends_on:
        return False
    qualification = qualification or faculty_qualification(faculty, subject, term)
    expected = scope_context(faculty, subject, term, qualification)
    if not expected['requirements']:
        return False  # Independent qualification does not require an exception.
    valid_ids = {o.pk: o.admin_user_id for o in overrides}
    covered = set()
    for evidence in CredentialApprovalEvidence.objects.filter(override_id__in=valid_ids):
        data = evidence.data
        if evidence.schema_version != 1 or not isinstance(data, dict):
            continue
        if (data.get('assignment_id') != assignment.pk or
                data.get('administrator_id') != valid_ids[evidence.override_id] or
                any(data.get(key) != value for key, value in expected.items() if key != 'requirements')):
            continue
        approved = data.get('requirements')
        if not isinstance(approved, list) or any(not isinstance(item, dict) for item in approved):
            continue
        for requirement in expected['requirements']:
            if requirement in approved:
                covered.add(requirement['id'])
    return covered == {item['id'] for item in expected['requirements']}


def teaching_eligibility(faculty, subject, term, assignment=None):
    result = faculty_qualification(faculty, subject, term)
    result["overridden"] = valid_credential_override(assignment, faculty, subject, term=term, qualification=result)
    result["eligible"] = result["qualified"] or result["overridden"]
    return result


def missing_credential_message(faculty, subject, term=None):
    result = faculty_qualification(faculty, subject, term)
    if result["qualified"]:
        return ""
    return (f"{faculty} does not meet the credential requirements for {subject}. " +
            " ".join(f"{item['required']}: " + " ".join(item["reasons"]) for item in result["missing"]) +
            " Credentials must be issued on or before the term ends and must not expire before that date. "
            "A blank expiry date means no expiry restriction. An authorized override requires a reason and verified approval for each missing requirement. Legacy free-text approvals do not establish that scope.")
