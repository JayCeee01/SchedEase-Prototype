def faculty_qualification(faculty, subject):
    requirements = list(subject.credential_requirements.select_related("required_credential").prefetch_related("acceptable_equivalents"))
    if not requirements:
        return {"qualified": True, "missing": [], "matched": []}

    faculty_names = set(faculty.credentials.select_related("credential").values_list("credential__name", flat=True))
    missing = []
    matched = []
    for requirement in requirements:
        accepted = [requirement.required_credential.name]
        accepted.extend(requirement.acceptable_equivalents.values_list("name", flat=True))
        if any(name in faculty_names for name in accepted):
            matched.append(requirement.required_credential.name)
        else:
            missing.append(
                {
                    "required": requirement.required_credential.name,
                    "acceptable": accepted,
                }
            )
    return {"qualified": not missing, "missing": missing, "matched": matched}


def missing_credential_message(faculty, subject):
    result = faculty_qualification(faculty, subject)
    if result["qualified"]:
        return ""
    parts = []
    for item in result["missing"]:
        equivalents = [name for name in item["acceptable"] if name != item["required"]]
        if equivalents:
            parts.append(f"{item['required']} (acceptable equivalents: {', '.join(equivalents)})")
        else:
            parts.append(item["required"])
    return f"{faculty} is missing required credential(s) for {subject}: {', '.join(parts)}."
