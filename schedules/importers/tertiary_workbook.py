import math
import re
import zipfile
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from xml.etree import ElementTree

from schedules.models import RoomKind, Weekday


MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

SAMPLE_ROWS = (12, 13, 15, 16, 21, 22, 23, 26, 76, 77, 205, 210, 341)
SAMPLE_SHEET = "TER SCHED 2T2526"
SELECTED_SECTIONS = (
    ("ACT", 1, "201"),
    ("BSCS", 3, "201"),
    ("BSAIS", 2, "201"),
)

PROGRAMS = {
    "ACT": ("CCS", "College of Computer Studies", "Associate in Computer Technology"),
    "BSCS": ("CCS", "College of Computer Studies", "Bachelor of Science in Computer Science"),
    "BSIT": ("CCS", "College of Computer Studies", "Bachelor of Science in Information Technology"),
    "BSAIS": ("CBA", "College of Business and Accountancy", "Bachelor of Science in Accounting Information Systems"),
    "BSCPE": ("COE", "College of Engineering", "Bachelor of Science in Computer Engineering"),
    "BSHM": ("CHM", "College of Hospitality Management", "Bachelor of Science in Hospitality Management"),
}

DAY_TOKENS = {"M": Weekday.MONDAY, "T": Weekday.TUESDAY, "W": Weekday.WEDNESDAY,
              "TH": Weekday.THURSDAY, "F": Weekday.FRIDAY, "S": Weekday.SATURDAY}


@dataclass(frozen=True)
class WorkbookRow:
    row_number: int
    section: str
    course_code: str
    description: str
    units: str
    days: str
    start: str
    end: str
    room: str
    instructor: str
    remarks: str


def _cell_value(cell, shared_strings):
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(MAIN_NS + "t"))
    value = cell.find(MAIN_NS + "v")
    if value is None:
        return ""
    return shared_strings[int(value.text)] if kind == "s" else value.text


def read_rows(path, sheet_name=SAMPLE_SHEET, row_numbers=SAMPLE_ROWS):
    """Read selected rows from xlsx using only the Python standard library."""
    path = Path(path)
    wanted = set(row_numbers)
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(MAIN_NS + "t")) for item in root]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        sheet = next((item for item in workbook.find(MAIN_NS + "sheets") if item.attrib["name"] == sheet_name), None)
        if sheet is None:
            raise ValueError(f"Sheet {sheet_name!r} was not found.")
        target = targets[sheet.attrib[REL_NS + "id"]].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        xml = ElementTree.fromstring(archive.read(target))
        result = []
        for row in xml.findall(".//" + MAIN_NS + "row"):
            number = int(row.attrib["r"])
            if number not in wanted:
                continue
            values = {}
            for cell in row.findall(MAIN_NS + "c"):
                column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                values[column] = _cell_value(cell, shared).strip()
            result.append(WorkbookRow(number, values.get("A", ""), values.get("B", ""), values.get("C", ""),
                                      values.get("D", ""), values.get("E", ""), values.get("F", ""),
                                      values.get("G", ""), values.get("H", ""), values.get("I", ""), values.get("J", "")))
    missing = wanted - {row.row_number for row in result}
    if missing:
        raise ValueError(f"Selected spreadsheet rows are missing: {sorted(missing)}")
    return sorted(result, key=lambda row: row.row_number)


def parse_section(value):
    match = re.fullmatch(r"(.+?)\s+([1-4])-(\d+)", value.strip())
    if not match:
        raise ValueError(f"Unsupported section value: {value!r}")
    return match.group(1).upper(), int(match.group(2)), match.group(3)


def parse_days(value):
    cleaned = value.upper().replace("/", "")
    tokens = re.findall(r"TH|M|T|W|F|S", cleaned)
    if not tokens or "".join(tokens) != cleaned:
        raise ValueError(f"Unsupported day value: {value!r}")
    return [DAY_TOKENS[token] for token in tokens]


def parse_time(value):
    value = value.strip()
    try:
        fraction = float(value)
    except ValueError:
        fraction = None
    if fraction is not None:
        minutes = round((fraction % 1) * 24 * 60)
        return time((minutes // 60) % 24, minutes % 60)
    compact = value.upper().replace(" ", "")
    for pattern in ("%I:%M%p", "%I%p", "%H:%M"):
        from datetime import datetime
        try:
            return datetime.strptime(compact, pattern).time()
        except ValueError:
            pass
    raise ValueError(f"Unsupported time value: {value!r}")


def duration_hours(start, end):
    minutes = end.hour * 60 + end.minute - start.hour * 60 - start.minute
    if minutes <= 0:
        raise ValueError("End time must be after start time.")
    return minutes / 60


def room_kind(room, description):
    room_upper = room.upper()
    description_upper = description.upper()
    if room_upper.startswith("CL"):
        return RoomKind.COMPUTER_LAB
    if "PHYLAB" in room_upper:
        return RoomKind.SCIENCE_LAB
    if room_upper.startswith("PEA"):
        return RoomKind.GYM
    if room_upper in {"KITCHEN", "KIT", "BAR", "HOTEL"}:
        return RoomKind.SPECIAL
    if "LAB" in description_upper:
        return RoomKind.SPECIAL
    return RoomKind.LECTURE


def normalized_title(value):
    title = re.sub(r"\s*[- ]?\((?:LAB|LEC)\)\s*$", "", value, flags=re.I)
    title = re.sub(r"\s*[- ](?:LAB|LEC)\s*$", "", title, flags=re.I)
    return re.sub(r"\s+", " ", title).strip()


def rounded_weekly_hours(hours):
    """The current model supports whole-hour GA blocks, so round upward visibly."""
    return max(1, math.ceil(hours))
