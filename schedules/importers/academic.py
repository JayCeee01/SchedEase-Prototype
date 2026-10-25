"""Bounded spreadsheet parsing and transactional academic-data import."""
from schedules.identity import identity_query, normalize_identity, RULES
import csv
from schedules.services import csv_export
import hashlib
import io
import json
import re
import zipfile
import zlib
from collections import Counter
from datetime import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.db import transaction
from schedules import models as m
from schedules.services.credentials import missing_credential_message, teaching_eligibility
from .tertiary_workbook import MAIN_NS, REL_NS, _cell_value
from .academic_sample import SAMPLE_ROWS

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
COLUMNS = {
    'department_code': 'Department identifier (required).',
    'department_name': 'Required for a new department.',
    'program_code': 'Program identifier (required).',
    'program_name': 'Required for a new program.',
    'year_level': 'Positive integer (required).',
    'year_label': 'Required for a new year level, e.g. Year 1.',
    'section_code': 'Section code only, e.g. 201 (required).',
    'section_size': 'Positive student count; required for a new section.',
    'course_code': 'Course identifier (required).',
    'course_description': 'Required for a new course.',
    'units': 'Nonnegative decimal with at most one decimal place; required for a new course.',
    'lecture_hours': 'Nonnegative integer weekly hours; required for a new course.',
    'lab_hours': 'Nonnegative integer weekly hours; required for a new course.',
    'course_room_type': 'Required for a new course: LECTURE, COMPUTER_LAB, SCIENCE_LAB, GYM, SPECIAL.',
    'assigned_faculty_id': 'Explicit teaching assignment employee ID (required). Mapping this fixes faculty for the GA.',
    'faculty_name': 'Required for a new faculty member.',
    'faculty_max_hours': 'Positive weekly workload limit; required for a new faculty member.',
    'faculty_credentials': 'Optional exact credential names separated by |. Adds only; never infers or removes credentials.',
    'course_credentials': 'Optional required credential names separated by |. Adds only.',
    'room_name': 'Optional room to create or match; does not fix a meeting to this room.',
    'room_type': 'Required for a new room: LECTURE, COMPUTER_LAB, SCIENCE_LAB, GYM, SPECIAL.',
    'room_capacity': 'Positive integer; required for a new room.',
    'component': 'LECTURE, LABORATORY or GENERAL (required).',
    'meeting_index': 'Positive integer unique within the assignment (required). One row per meeting.',
    'duration_minutes': 'Positive integer, at most 720 (required). Component totals must match course hours.',
    'meeting_room_type': 'Optional required room type for this meeting (especially labs).',
    'availability_owner': 'Optional explicit constraint: FACULTY or ROOM. Uses assigned_faculty_id or room_name.',
    'availability_day': 'Monday through Saturday, or 0 through 5.',
    'availability_start': 'HH:MM, between 07:00 and 19:00.',
    'availability_end': 'HH:MM, after start, at most 19:00.',
    'availability_kind': 'FACULTY supports UNAVAILABLE/PREFERRED; ROOM supports AVAILABLE/UNAVAILABLE.',
    'reference_faculty': 'Original instructor, reference only.',
    'reference_room': 'Original room, reference only.',
    'reference_day': 'Original day, reference only.',
    'reference_start': 'Original start time, reference only.',
    'reference_end': 'Original end time, reference only.',
}
REQUIRED = {'department_code', 'program_code', 'year_level', 'section_code', 'course_code',
            'assigned_faculty_id', 'component', 'meeting_index', 'duration_minutes'}
ALIASES = {'subject_code': 'course_code', 'course_title': 'course_description', 'subject_title': 'course_description',
           'instructor': 'reference_faculty', 'faculty': 'reference_faculty', 'day': 'reference_day',
           'room': 'reference_room', 'start_time': 'reference_start', 'end_time': 'reference_end'}

# Translate model validation fields to spreadsheet columns without changing validation.
MODEL_COLUMNS = {
    'Department': {'code': 'department_code', 'name': 'department_name'},
    'Program': {'code': 'program_code', 'name': 'program_name', 'department': 'department_code'},
    'YearLevel': {'level': 'year_level', 'label': 'year_label'},
    'Section': {'name': 'section_code', 'size': 'section_size', 'program': 'program_code', 'year_level': 'year_level'},
    'Subject': {'code': 'course_code', 'title': 'course_description', 'required_room_type': 'course_room_type',
                'units': 'units', 'lecture_hours': 'lecture_hours', 'lab_hours': 'lab_hours'},
    'Faculty': {'employee_id': 'assigned_faculty_id', 'full_name': 'faculty_name', 'max_weekly_hours': 'faculty_max_hours'},
    'Room': {'name': 'room_name', 'room_type': 'room_type', 'capacity': 'room_capacity'},
    'TeachingAssignment': {'component': 'component', 'meeting_index': 'meeting_index', 'duration_minutes': 'duration_minutes',
                           'required_room_type_override': 'meeting_room_type', 'faculty': 'assigned_faculty_id'},
    'Availability': {'day': 'availability_day', 'start_time': 'availability_start', 'end_time': 'availability_end', 'kind': 'availability_kind'},
}


def suggested_mapping(header):
    key = re.sub(r'[^a-z0-9]+', '_', header.lower()).strip('_')
    return key if key in COLUMNS else ALIASES.get(key, '')


def xml(data):
    if b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML entities and document types are not accepted.')
    return ET.fromstring(data)


def read_spreadsheet(upload):
    if upload.size > MAX_BYTES:
        raise ValueError('Upload must be 5 MB or smaller.')
    content = upload.read(MAX_BYTES + 1)
    suffix = Path(upload.name).suffix.lower()
    rows = []
    try:
        if suffix == '.csv':
            reader = csv.reader(io.StringIO(content.decode('utf-8-sig')), strict=True)
            for number, values in enumerate(reader, 1):
                rows.append((number, values))
                if len(rows) > MAX_ROWS + 1:
                    raise ValueError('Maximum 1,000 data rows per upload.')
        elif suffix == '.xlsx':
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = archive.infolist()
                if len(infos) > 500 or sum(i.file_size for i in infos) > 25 * 1024 * 1024:
                    raise ValueError('Workbook expands beyond the 25 MB content limit.')
                if any(i.flag_bits & 1 for i in infos):
                    raise ValueError('Encrypted workbooks are not supported.')
                if any('vbaproject' in i.filename.lower() or 'externallinks/' in i.filename.lower() for i in infos):
                    raise ValueError('Macros and external workbook links are not accepted.')
                workbook = xml(archive.read('xl/workbook.xml'))
                sheets = workbook.find(MAIN_NS + 'sheets')
                if len(sheets) != 1:
                    raise ValueError('Use a workbook with exactly one worksheet and a header in row 1.')
                targets = {n.attrib['Id']: n.attrib['Target'] for n in xml(archive.read('xl/_rels/workbook.xml.rels'))}
                target = targets[sheets[0].attrib[REL_NS + 'id']].lstrip('/')
                if not target.startswith('xl/'):
                    target = 'xl/' + target
                shared = []
                if 'xl/sharedStrings.xml' in archive.namelist():
                    shared = [''.join(t.text or '' for t in n.iter(MAIN_NS + 't'))
                              for n in xml(archive.read('xl/sharedStrings.xml'))]
                sheet = xml(archive.read(target))
                if sheet.find(MAIN_NS + 'mergeCells') is not None:
                    raise ValueError('Merged cells are not supported; use one row per meeting.')
                for row in sheet.findall('.//' + MAIN_NS + 'row'):
                    values = []
                    for cell in row.findall(MAIN_NS + 'c'):
                        if cell.find(MAIN_NS + 'f') is not None or cell.attrib.get('t') == 'e':
                            raise ValueError(f"Row {row.attrib['r']}, {cell.attrib['r']}: replace formulas/errors with plain values.")
                        letters = re.match(r'[A-Z]+', cell.attrib['r']).group()
                        index = 0
                        for letter in letters:
                            index = index * 26 + ord(letter) - 64
                        if index > 80:
                            raise ValueError('Maximum 80 columns.')
                        values.extend([''] * (index - len(values)))
                        values[index - 1] = _cell_value(cell, shared)
                    rows.append((int(row.attrib['r']), values))
                    if len(rows) > MAX_ROWS + 1:
                        raise ValueError('Maximum 1,000 data rows per upload.')
        else:
            raise ValueError('Only .csv and .xlsx files are accepted.')
    except (UnicodeError, csv.Error, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError,
            AttributeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise ValueError('Invalid spreadsheet. Use UTF-8 CSV or a valid single-sheet XLSX file.') from exc
    if not rows or rows[0][0] != 1:
        raise ValueError('A header row is required in row 1.')
    headers = [str(v).strip() for v in rows[0][1]]
    if not headers or len(headers) > 80 or any(not h for h in headers) or len(set(h.casefold() for h in headers)) != len(headers):
        raise ValueError('Provide 1-80 unique, nonempty column headers.')
    data = []
    for number, values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        if len(values) > len(headers) or any(len(str(v)) > 2000 or '\x00' in str(v) for v in values):
            raise ValueError(f'Row {number}: extra columns, NUL characters, or a cell exceeding 2,000 characters.')
        data.append({'number': number, 'values': [str(v).strip() for v in values] + [''] * (len(headers) - len(values))})
    if not data:
        raise ValueError('The spreadsheet contains no data rows.')
    return {'headers': headers, 'rows': data}


def template_bytes(xlsx=False, include_samples=True):
    headers = list(COLUMNS)
    rows = [headers] + ([[row.get(key, '') for key in headers] for row in SAMPLE_ROWS] if include_samples else [])
    if not xlsx:
        stream = io.StringIO(newline='')
        csv_export.writer(stream).writerows(rows)
        return stream.getvalue().encode('utf-8-sig')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="' + MAIN_NS[1:-1] + '" xmlns:r="' + REL_NS[1:-1] + '"><sheets><sheet name="Academic data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        sheet_rows = []
        for number, values in enumerate(rows, 1):
            cells = []
            for index, value in enumerate(values, 1):
                letters = ''
                while index:
                    index, rem = divmod(index - 1, 26)
                    letters = chr(65 + rem) + letters
                style = ' s="1"' if number == 1 and value in REQUIRED else ''
                cells.append(f'<c r="{letters}{number}" t="inlineStr"{style}><is><t>{escape(value)}</t></is></c>')
            sheet_rows.append(f'<row r="{number}">' + ''.join(cells) + '</row>')
        z.writestr('xl/styles.xml', '<styleSheet xmlns="' + MAIN_NS[1:-1] + '"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf xfId="0"/><xf fontId="1" fillId="2" xfId="0" applyFont="1" applyFill="1"/></cellXfs></styleSheet>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="' + MAIN_NS[1:-1] + '"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="36" width="24" customWidth="1"/></cols><sheetData>' + ''.join(sheet_rows) + '</sheetData></worksheet>')
    return stream.getvalue()


def mapped_rows(payload, mapping):
    selected = [key for key in mapping if key]
    if len(mapping) != len(payload['headers']) or any(key not in COLUMNS for key in selected):
        raise ValueError('Invalid column mapping.')
    if len(selected) != len(set(selected)):
        raise ValueError('Each destination column may be mapped only once.')
    missing = REQUIRED - set(selected)
    if missing:
        raise ValueError('Map required columns: ' + ', '.join(sorted(missing)))
    return [(r['number'], {key: value for key, value in zip(mapping, r['values']) if key}) for r in payload['rows']]


class Importer:
    def __init__(self, term, policy):
        self.term, self.policy = term, policy
        self.actions, self.errors, self.warnings = [], [], []
        self.seen = {}
        self.parents = set()
        self.updated = {}
        self.row = 0
        self.issues = []
        self.issue_rows = None
        self.parent_rows = {}

    def error(self, column, message, columns=None):
        self.errors.append(f'Row {self.row}, {column}: {message}')
        if columns is None:
            columns = [key for key in COLUMNS if re.search(r'\b' + re.escape(key) + r'\b', message)]
            if column in COLUMNS:
                columns.append(column)
            for model, fields in MODEL_COLUMNS.items():
                if message.startswith(model + ':') or message.startswith(model + '.'):
                    columns.extend(value for field, value in fields.items() if re.search(r'\b' + field + r'\b', message))
            if 'ConversionSyntax' in message:
                columns = ['units']
            if 'isoformat' in message:
                columns = ['availability_start', 'availability_end']
        for row in self.issue_rows if self.issue_rows is not None else [self.row]:
            self.issues.append({'row': row, 'columns': sorted(set(columns)), 'problem': message})

    def integer(self, value, column, minimum=0):
        if not re.fullmatch(r'\d+', value) or int(value) < minimum:
            raise ValueError(f'{column}: expected an integer of at least {minimum}.')
        return int(value)

    def upsert(self, model, keys, values, required=()):
        identity = (model.__name__, tuple((k, normalize_identity(str(getattr(v, "pk", v))) if k in RULES.get(model.__name__, ((), ()))[0] else str(getattr(v, "pk", v))) for k, v in keys.items()))
        provided = {k: v for k, v in values.items() if v is not None}
        obj = identity_query(model, keys).first()
        if identity in self.seen:
            old = self.seen[identity]
            for key, value in provided.items():
                if key in old and old[key] != value:
                    raise ValueError(f'{model.__name__}.{key}: conflicting values for the same record in this file.')
            # Require repeated rows to supply consistent attributes, including blanks.
            if old != provided:
                raise ValueError(f'{model.__name__}: repeat the same attributes on every row for this record.')
            if model == m.TeachingAssignment:
                self.warnings.append(f'Row {self.row}: duplicate meeting in this file; included only once.')
            return obj
        self.seen[identity] = provided
        before = {f.attname: str(getattr(obj, f.attname)) for f in model._meta.fields if f.name not in ('created_at', 'updated_at')} if obj else {}
        action = 'created' if obj is None else 'skipped'
        if obj is None:
            missing = [key for key in required if key not in provided]
            if missing:
                raise ValueError(f'{model.__name__}: missing required fields: {", ".join(missing)}.')
            obj = model(**keys, **provided)
        elif self.policy == 'update':
            if any(getattr(obj, key) != value for key, value in provided.items()):
                action = 'updated'
                for key, value in provided.items():
                    setattr(obj, key, value)
                self.updated.setdefault(model, set()).add(obj.pk)
        elif any(getattr(obj, key) != value for key, value in provided.items()):
            self.warnings.append(f'Row {self.row}: existing {model.__name__} {obj} differs; database values retained.')
        try:
            obj.full_clean()
        except ValidationError as exc:
            exc.import_columns = [MODEL_COLUMNS.get(model.__name__, {}).get(key, key)
                                  for key in getattr(exc, 'message_dict', {}) if key != '__all__']
            raise
        if action != 'skipped':
            obj.save()
        after = {key: str(getattr(value, 'pk', value)) for key, value in {**keys, **provided}.items()}
        self.actions.append({'row': self.row, 'module': model.__name__, 'record': str(obj), 'action': action, 'before': before, 'provided': after})
        return obj

    def entities(self, r):
        def val(key):
            return r.get(key) or None
        def num(key, minimum=0):
            return self.integer(r[key], key, minimum) if r.get(key) else None
        for key in REQUIRED:
            if not r.get(key):
                raise ValueError(f'{key}: required value is missing.')
        department = self.upsert(m.Department, {'code': r['department_code']}, {'name': val('department_name')}, ['name'])
        program = self.upsert(m.Program, {'code': r['program_code']}, {'name': val('program_name'), 'department': department}, ['name'])
        year = self.upsert(m.YearLevel, {'level': num('year_level', 1)}, {'label': val('year_label')}, ['label'])
        section = self.upsert(m.Section, {'program': program, 'year_level': year, 'name': r['section_code'].upper()}, {'size': num('section_size', 1)}, ['size'])
        units = Decimal(r['units']) if val('units') else None
        if units is not None and (not units.is_finite() or units < 0):
            raise ValueError('units: enter a finite nonnegative decimal.')
        subject = self.upsert(m.Subject, {'code': r['course_code']}, {
            'title': val('course_description'), 'department': department, 'units': units,
            'lecture_hours': num('lecture_hours'), 'lab_hours': num('lab_hours'), 'required_room_type': val('course_room_type')},
            ['title', 'units', 'lecture_hours', 'lab_hours', 'required_room_type'])
        faculty = self.upsert(m.Faculty, {'employee_id': r['assigned_faculty_id']}, {
            'department': department, 'full_name': val('faculty_name'), 'max_weekly_hours': num('faculty_max_hours', 1)}, ['full_name', 'max_weekly_hours'])
        room = None
        if val('room_name'):
            room = self.upsert(m.Room, {'name': r['room_name']}, {'room_type': val('room_type'), 'capacity': num('room_capacity', 1)}, ['room_type', 'capacity'])
            from schedules.services.availability import AvailabilityPolicy
            reason = AvailabilityPolicy.for_resource(room).active_rejection_reason()
            if reason:
                raise ValueError('room_name: Room ' + reason)
        elif val('room_type') or val('room_capacity'):
            raise ValueError('room_name: required when room attributes are supplied.')
        for column, model, owner in [('faculty_credentials', m.FacultyCredential, {'faculty': faculty}),
                                     ('course_credentials', m.SubjectCredentialRequirement, {'subject': subject})]:
            for name in sorted(set((r.get(column) or '').split('|')) - {''}):
                credential = self.upsert(m.Credential, {'name': name.strip()}, {})
                field = 'credential' if model == m.FacultyCredential else 'required_credential'
                self.upsert(model, {**owner, field: credential}, {})
        fields = ['availability_owner', 'availability_day', 'availability_start', 'availability_end', 'availability_kind']
        if any(val(k) for k in fields):
            if not all(val(k) for k in fields):
                raise ValueError('availability: supply owner, day, start, end and kind together.')
            owner = r['availability_owner']
            if owner not in ('FACULTY', 'ROOM') or (owner == 'ROOM' and room is None):
                raise ValueError('availability_owner: choose FACULTY, or ROOM with room_name.')
            supported = {'FACULTY': {'UNAVAILABLE', 'PREFERRED'}, 'ROOM': {'AVAILABLE', 'UNAVAILABLE'}}
            if r['availability_kind'] not in supported[owner]:
                raise ValueError('availability_kind: the GA supports FACULTY UNAVAILABLE/PREFERRED and ROOM AVAILABLE/UNAVAILABLE.')
            days = {label.lower(): str(value) for value, label in m.Weekday.choices}
            day = days.get(r['availability_day'].lower(), r['availability_day'])
            start, end = time.fromisoformat(r['availability_start']), time.fromisoformat(r['availability_end'])
            if not time(7) <= start < end <= time(19):
                raise ValueError('availability_start/end: use an interval within 07:00-19:00.')
            action_count = len(self.actions)
            self.upsert(m.Availability, {'faculty': faculty if owner == 'FACULTY' else None,
                'room': room if owner == 'ROOM' else None, 'day': self.integer(day, 'availability_day'),
                'start_time': start, 'end_time': end, 'kind': r['availability_kind']}, {})
            if len(self.actions) > action_count and self.actions[-1]['action'] == 'created':
                self.updated.setdefault(m.Faculty if owner == 'FACULTY' else m.Room, set()).add(faculty.pk if owner == 'FACULTY' else room.pk)
        return section, subject, faculty

    def meeting(self, r, entities):
        section, subject, faculty = entities
        duration = self.integer(r['duration_minutes'], 'duration_minutes', 1)
        from schedules.services.meetings import duration_errors
        errors = duration_errors(duration)
        if errors:
            raise ValueError("duration_minutes: " + "; ".join(errors))
        index = self.integer(r['meeting_index'], 'meeting_index', 1)
        keys = {'term': self.term, 'subject': subject, 'section': section,
                'component': r['component'], 'meeting_index': index}
        existing = m.TeachingAssignment.objects.filter(**keys).first()
        if not teaching_eligibility(faculty, subject, self.term, existing)['eligible']:
            raise ValueError('assigned_faculty_id: ' + missing_credential_message(faculty, subject, self.term))
        if existing and self.policy == 'skip':
            parent = existing.assignment
        else:
            # Published/generated entries must not silently change through their shared assignment.
            if existing and existing.scheduleentry_set.exists():
                changes = (existing.faculty_id != faculty.pk or existing.duration_minutes != duration
                           or (r.get('meeting_room_type') and existing.required_room_type_override != r['meeting_room_type']))
                if changes:
                    raise ValueError('meeting_index: this meeting is used by a schedule; edit it through the existing schedule workflow.')
            parent = self.upsert(m.Assignment, {'term': self.term, 'subject': subject, 'section': section, 'faculty': faculty}, {})
        meeting = self.upsert(m.TeachingAssignment, keys, {'faculty': faculty, 'assignment': parent,
            'duration_minutes': duration, 'required_room_type_override': r.get('meeting_room_type') or None})
        if meeting.assignment_id:
            self.parents.add(meeting.assignment_id)
            self.parent_rows.setdefault(meeting.assignment_id, []).append(self.row)

    def validate_result(self):
        # Include all assignments: changing shared courses or credentials must not invalidate other terms.
        subject_ids = m.Assignment.objects.filter(pk__in=self.parents).values_list('subject_id', flat=True)
        for parent in m.Assignment.objects.filter(subject_id__in=subject_ids).select_related('subject', 'faculty'):
            self.issue_rows = self.parent_rows.get(parent.pk, [None])
            meetings = list(parent.meetings.all())
            from schedules.services.room_compatibility import meeting_room_errors
            for meeting in meetings:
                for message in meeting_room_errors(meeting, parent.subject):
                    self.error('meeting_room_type', message)
            from schedules.services.meetings import meeting_requirement_errors, meeting_records
            for column, message in meeting_requirement_errors(parent.subject, meeting_records(meetings)):
                self.error(column, f'{parent}: {message}')
            problem = missing_credential_message(parent.faculty, parent.subject, parent.term)
            if problem and not all(teaching_eligibility(parent.faculty, parent.subject, parent.term, meeting)['eligible'] for meeting in meetings):
                self.error('faculty_credentials', problem)
        self.issue_rows = [None]
        if self.updated:
            from django.db.models import Q
            affected = Q(pk__in=[])
            for model, lookup in [(m.Subject, 'assignment__subject_id'), (m.Section, 'assignment__section_id'),
                                  (m.Faculty, 'assignment__faculty_id'), (m.Room, 'room_id')]:
                affected |= Q(**{lookup + '__in': self.updated.get(model, set())})
            for model, lookup in [(m.Subject, 'subject_override_id'), (m.Section, 'section_override_id'), (m.Faculty, 'faculty_override_id')]:
                affected |= Q(**{lookup + '__in': self.updated.get(model, set())})
            for entry in m.ScheduleEntry.objects.filter(affected):
                try:
                    entry.full_clean()
                except ValidationError as exc:
                    self.error('update', f'Would invalidate schedule entry {entry.pk}: ' + '; '.join(exc.messages))
        from schedules.services.ga import GeneticScheduler
        for warning in GeneticScheduler(self.term, m.GASettings()).preflight_issues():
            self.warnings.append('Generation readiness: ' + warning)
        self.warnings.append('No availability is inferred. Review room/faculty availability and GA settings before generating. Original timetable columns are reference only; fixed day/time/room slots are not supported.')


def run_import(payload, mapping, term, policy='skip', commit=False, expected_signature=None):
    if policy not in ('skip', 'update'):
        raise ValueError('Choose skip or update.')
    rows = mapped_rows(payload, mapping)
    importer = Importer(term, policy)
    with transaction.atomic():
        prepared = []
        for number, row in rows:
            importer.row = number
            seen_before, action_count = dict(importer.seen), len(importer.actions)
            try:
                with transaction.atomic():
                    prepared.append((number, row, importer.entities(row)))
            except (ValueError, InvalidOperation, ValidationError) as exc:
                importer.seen = seen_before
                del importer.actions[action_count:]
                importer.error('data', '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc), getattr(exc, 'import_columns', None))
        if not importer.errors:
            for number, row, entities in prepared:
                importer.row = number
                try:
                    with transaction.atomic():
                        importer.meeting(row, entities)
                except (ValueError, ValidationError) as exc:
                    importer.error('meeting', '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc), getattr(exc, 'import_columns', None))
            importer.validate_result()
        result = {'total': len(rows), 'actions': importer.actions, 'errors': importer.errors, 'issues': importer.issues,
                  'warnings': list(dict.fromkeys(importer.warnings)), 'counts': dict(Counter(a['action'] for a in importer.actions))}
        signature = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        result['signature'] = signature
        if commit and expected_signature != signature:
            raise ValueError('Data changed since preview. Validate and review a fresh preview before confirming.')
        if not commit or importer.errors:
            transaction.set_rollback(True)
        return result
