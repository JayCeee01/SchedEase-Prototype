import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from xml.etree import ElementTree

from schedules.models import RoomKind, TeachingAssignment, Weekday


M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
DATA_SHEET = "TER SCHED 2T2526"
PROGRAMS = {
    "ACT": ("CCS", "College of Computer Studies", "Associate in Computer Technology"),
    "BSCS": ("CCS", "College of Computer Studies", "Bachelor of Science in Computer Science"),
    "BSIT": ("CCS", "College of Computer Studies", "Bachelor of Science in Information Technology"),
    "OS-BSIT": ("CCS", "College of Computer Studies", "Online Bachelor of Science in Information Technology"),
    "BSAIS": ("CBA", "College of Business and Accountancy", "Bachelor of Science in Accounting Information Systems"),
    "BSCPE": ("COE", "College of Engineering", "Bachelor of Science in Computer Engineering"),
    "BSHM": ("CHM", "College of Hospitality Management", "Bachelor of Science in Hospitality Management"),
    "OS-BSHM": ("CHM", "College of Hospitality Management", "Online Bachelor of Science in Hospitality Management"),
    "BSTM": ("CHM", "College of Hospitality Management", "Bachelor of Science in Tourism Management"),
}
DAY_MAP = {"M": Weekday.MONDAY, "T": Weekday.TUESDAY, "W": Weekday.WEDNESDAY,
           "TH": Weekday.THURSDAY, "F": Weekday.FRIDAY, "S": Weekday.SATURDAY}
ROOM_ALIASES = {"KIT": "KITCHEN", "PEAA2": "PEA2"}
CAPACITY_DEFAULTS = {RoomKind.LECTURE: 45, RoomKind.COMPUTER_LAB: 40,
                     RoomKind.SCIENCE_LAB: 35, RoomKind.GYM: 60, RoomKind.SPECIAL: 30}


def _value(cell, shared):
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(M + "t"))
    value = cell.find(M + "v")
    if value is None:
        return ""
    return shared[int(value.text)] if cell.attrib.get("t") == "s" else value.text


def workbook_rows(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(n.text or "" for n in item.iter(M + "t"))
                      for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))]
        book = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        for sheet in book.find(M + "sheets"):
            target = targets[sheet.attrib[R + "id"]].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            rows = []
            for row in ElementTree.fromstring(archive.read(target)).findall(".//" + M + "row"):
                values = {}
                for cell in row.findall(M + "c"):
                    column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                    values[column] = _value(cell, shared).strip()
                rows.append((int(row.attrib["r"]), values))
            result[sheet.attrib["name"]] = rows
    return result


def clean_text(value):
    return re.sub(r"\s+", " ", value.strip())


def section_parts(value):
    match = re.fullmatch(r"(.+?)\s+([1-4])-(\d+)", clean_text(value).upper())
    if not match:
        raise ValueError(f"unrecognized section {value!r}")
    return match.group(1), int(match.group(2)), match.group(3)


def days(value):
    cleaned = re.sub(r"[\s/]", "", value.upper())
    tokens = re.findall(r"TH|M|T|W|F|S", cleaned)
    if not tokens or "".join(tokens) != cleaned:
        raise ValueError(f"unrecognized days {value!r}")
    return [DAY_MAP[token] for token in tokens]


def _time_candidates(value):
    raw = value.strip().upper().replace(";", ":").replace(" ", "")
    try:
        fraction = float(raw)
    except ValueError:
        fraction = None
    if fraction is not None:
        minutes = round((fraction % 1) * 1440)
        candidates = {minutes}
        if minutes < 12 * 60:
            candidates.add(minutes + 12 * 60)
        return sorted(candidates)
    explicit = raw.endswith("AM") or raw.endswith("PM")
    for fmt in ("%I:%M:%S%p", "%I:%M%p", "%I%p", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            base = parsed.hour * 60 + parsed.minute
            if explicit or fmt.startswith("%H") and parsed.hour > 12:
                return [base]
            candidates = {base, base + 720 if base < 720 else base - 720}
            return sorted(candidates)
        except ValueError:
            pass
    raise ValueError(f"unrecognized time {value!r}")


def time_pair(start_value, end_value):
    choices = []
    for start in _time_candidates(start_value):
        for end in _time_candidates(end_value):
            duration = end - start
            if 7 * 60 <= start < end <= 23 * 60 and 30 <= duration <= 6 * 60:
                choices.append((abs(duration - 90), start, end))
    if not choices:
        raise ValueError(f"cannot resolve time range {start_value!r}-{end_value!r}")
    _, start, end = min(choices)
    return time(start // 60, start % 60), time(end // 60, end % 60), end - start


def component(description):
    text = description.upper()
    if "LAB" in text:
        return TeachingAssignment.Component.LABORATORY
    if "LEC" in text:
        return TeachingAssignment.Component.LECTURE
    return TeachingAssignment.Component.GENERAL


def room_type(name):
    upper = name.upper()
    if upper.startswith("CL"):
        return RoomKind.COMPUTER_LAB
    if "PHYLAB" in upper:
        return RoomKind.SCIENCE_LAB
    if upper.startswith("PEA"):
        return RoomKind.GYM
    if upper in {"KITCHEN", "BAR", "HOTEL"}:
        return RoomKind.SPECIAL
    return RoomKind.LECTURE


def subject_title(value):
    value = re.sub(r"\s*[- ]?\((LAB|LEC)\)\s*$", "", value, flags=re.I)
    value = re.sub(r"\s*[- ](?:LAB|LEC)\s*$", "", value, flags=re.I)
    return clean_text(value)


def normalize_room(value, audit, sheet, row):
    original = clean_text(value).upper()
    normalized = ROOM_ALIASES.get(original, original)
    if original != normalized:
        audit.append({"sheet": sheet, "row": row, "field": "room", "original": original,
                      "normalized": normalized, "reason": "explicit workbook typo/abbreviation alias"})
    return normalized


def normalized_meetings(path):
    sheets = workbook_rows(path)
    if DATA_SHEET not in sheets:
        raise ValueError(f"required normalized sheet {DATA_SHEET!r} is missing")
    audit, rejected, meetings = [], [], []
    for row_number, row in sheets[DATA_SHEET]:
        if not row.get("B") or row.get("B") == "COURSE CODE":
            continue
        try:
            program, year, section = section_parts(row.get("A", ""))
            if program not in PROGRAMS:
                raise ValueError(f"no program mapping for {program}")
            day_values = days(row.get("E", ""))
            starts = [item.strip() for item in row.get("F", "").split("/") if item.strip()]
            ends = [item.strip() for item in row.get("G", "").split("/") if item.strip()]
            rooms = [item.strip() for item in row.get("H", "").split("/") if item.strip()]
            if len(starts) == 1:
                starts *= len(day_values)
            if len(ends) == 1:
                ends *= len(day_values)
            if len(rooms) == 1:
                rooms *= len(day_values)
            if not (len(day_values) == len(starts) == len(ends) == len(rooms)):
                raise ValueError("day/time/room occurrence counts do not match")
            code = re.sub(r"\s+", "", row.get("B", "").upper())
            instructor = clean_text(row.get("I", "")).upper()
            if not code or not instructor:
                raise ValueError("missing subject code or instructor")
            for occurrence, (day, start_raw, end_raw, room_raw) in enumerate(zip(day_values, starts, ends, rooms), 1):
                start, end, duration = time_pair(start_raw, end_raw)
                room = normalize_room(room_raw, audit, DATA_SHEET, row_number)
                meetings.append({"sheet": DATA_SHEET, "row": row_number, "occurrence": occurrence,
                    "source_key": f"{DATA_SHEET}:{row_number}:{occurrence}", "program": program, "year": year,
                    "section": section, "code": code, "title": subject_title(row.get("C", "")),
                    "original_title": clean_text(row.get("C", "")), "units": row.get("D", ""),
                    "faculty": instructor, "day": day, "start": start, "end": end, "duration": duration,
                    "room": room, "room_type": room_type(room), "component": component(row.get("C", "")),
                    "remarks": clean_text(row.get("J", ""))})
        except ValueError as exc:
            rejected.append({"sheet": DATA_SHEET, "row": row_number, "reason": str(exc), "values": row})
    exact = Counter((m["program"], m["year"], m["section"], m["code"], m["faculty"], m["day"], m["start"], m["end"], m["room"]) for m in meetings)
    duplicates = [dict(zip(("program", "year", "section", "code", "faculty", "day", "start", "end", "room"), key), count=count)
                  for key, count in exact.items() if count > 1]
    data_rows = [(number, row) for number, row in sheets[DATA_SHEET]
                 if row.get("B") and row.get("B") != "COURSE CODE"]
    missing_columns = {name: sum(1 for _, row in data_rows if not row.get(column)) for name, column in {
        "section": "A", "subject_code": "B", "subject_name": "C", "units": "D", "days": "E",
        "start_time": "F", "end_time": "G", "room": "H", "faculty": "I"}.items()}
    lecture_meetings = sum(m["component"] == TeachingAssignment.Component.LECTURE for m in meetings)
    laboratory_meetings = sum(m["component"] == TeachingAssignment.Component.LABORATORY for m in meetings)
    analysis = {"workbooks_processed": 1, "workbook_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "worksheets": {name: {"physical_rows": len(rows), "course_rows": sum(1 for _, r in rows if r.get("B") and r.get("B") != "COURSE CODE"),
                              "complete_relational_rows": sum(1 for _, r in rows if r.get("A") and r.get("B") not in {"", "COURSE CODE"} and r.get("I"))}
                       for name, rows in sheets.items()},
        "data_sheet": DATA_SHEET, "source_rows": len({m["row"] for m in meetings}), "expanded_meetings": len(meetings),
        "rejected_rows": len(rejected), "programs": sorted({m["program"] for m in meetings}),
        "year_levels": sorted({m["year"] for m in meetings}), "sections": len({(m["program"], m["year"], m["section"]) for m in meetings}),
        "subjects": len({m["code"] for m in meetings}), "faculty": len({m["faculty"] for m in meetings}),
        "rooms": len({m["room"] for m in meetings}), "duplicate_signatures": len(duplicates),
        "lecture_meetings": lecture_meetings, "laboratory_meetings": laboratory_meetings,
        "general_meetings": len(meetings) - lecture_meetings - laboratory_meetings,
        "normalization_events": len(audit),
        "data_quality": {"rows_processed": len(data_rows), "rows_importable": len({m["row"] for m in meetings}),
            "rows_unresolved": len(rejected), "missing_values_by_field": missing_columns,
            "exact_duplicate_signatures": len(duplicates), "normalization_events": len(audit),
            "derived_duration_values": len(meetings), "derived_day_values": len(meetings),
            "default_section_sizes": len({(m["program"], m["year"], m["section"]) for m in meetings}),
            "default_room_capacities": len({m["room"] for m in meetings}),
            "credentials_available_in_workbook": False}}
    return meetings, audit, rejected, duplicates, analysis


def write_reports(directory, analysis, audit, rejected, duplicates, conflicts=None, utilization=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "analysis.json").open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, indent=2, default=str)
    with (directory / "data_quality.json").open("w", encoding="utf-8") as handle:
        json.dump(analysis.get("data_quality", {}), handle, indent=2, default=str)
    import_summary = {key: analysis.get(key) for key in ("workbooks_processed", "source_rows", "expanded_meetings",
        "rejected_rows", "programs", "year_levels", "sections", "subjects", "faculty", "rooms",
        "lecture_meetings", "laboratory_meetings", "general_meetings", "duplicate_signatures", "normalization_events")}
    import_summary["worksheets_processed"] = len(analysis.get("worksheets", {}))
    with (directory / "import_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(import_summary, handle, indent=2, default=str)
    with (directory / "normalizations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sheet", "row", "field", "original", "normalized", "reason"])
        writer.writeheader(); writer.writerows(audit)
    for name, value in (("rejected_rows.json", rejected), ("duplicate_signatures.json", duplicates),
                        ("original_conflicts.json", conflicts or []), ("room_utilization.json", utilization or [])):
        with (directory / name).open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, default=str)
