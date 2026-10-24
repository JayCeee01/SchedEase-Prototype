from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, RequestFactory

from . import models as m
from .forms import MODEL_FORMS
from .identity import identity_get_or_create
from .importers.academic import Importer


class IdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = m.Department.objects.create(code="CS", name="Computing")
        cls.program = m.Program.objects.create(code="BSCS", name="Program", department=cls.department)
        cls.year = m.YearLevel.objects.create(level=1, label="First")
        cls.section = m.Section.objects.create(program=cls.program, year_level=cls.year, name="A")
        cls.faculty = m.Faculty.objects.create(employee_id="EMP001A", full_name="Same Name", department=cls.department)
        cls.student = m.Student.objects.create(student_number="001234", full_name="Same Name", section=cls.section)
        cls.term = m.AcademicTerm.objects.create(name="Term One", school_year="2026", starts_on=date(2026, 1, 1), ends_on=date(2026, 6, 1))

    def test_global_identities_reject_case_and_whitespace(self):
        examples = [
            (m.Department, dict(code="cs", name="Other"), "code"),
            (m.Program, dict(code="bscs", name="Other", department=self.department), "code"),
            (m.Faculty, dict(employee_id="emp001a", full_name="Other", department=self.department), "employee_id"),
            (m.Student, dict(student_number="001234", full_name="Other", section=self.section), "student_number"),
        ]
        for model, values, field in examples:
            for variant in (values[field], "\t " + values[field] + "\n\u00a0"):
                with self.subTest(model=model.__name__, variant=repr(variant)):
                    obj = model(**{**values, field: variant})
                    with self.assertRaises(ValidationError) as error:
                        obj.full_clean()
                    self.assertIn(field, error.exception.message_dict)
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        model.objects.create(**{**values, field: variant})

    def test_names_and_course_code(self):
        cases = [
            (m.Room, dict(name="Lab A", capacity=60, room_type="LECTURE"), "name"),
            (m.Credential, dict(name="Straße Certificate"), "name"),
            (m.Subject, dict(code="CS101", title="Course", department=self.department), "code"),
        ]
        for model, values, field in cases:
            obj = model.objects.create(**values)
            duplicate = {**values, field: " " + values[field].swapcase() + " "}
            with self.assertRaises(ValidationError) as error:
                model(**duplicate).full_clean()
            self.assertIn(field, error.exception.message_dict)
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.bulk_create([model(**duplicate)])
            obj.full_clean()

    def test_term_and_section_scopes(self):
        duplicate = m.AcademicTerm(name=" term ONE ", school_year=" 2026 ", starts_on=date(2026, 1, 1), ends_on=date(2026, 6, 1))
        with self.assertRaises(ValidationError) as error:
            duplicate.full_clean()
        self.assertIn("name", error.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()
        duplicate.school_year = "2027"
        duplicate.full_clean()
        duplicate.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.bulk_create([m.Section(program=self.program, year_level=self.year, name=" a ")])
        year = m.YearLevel.objects.create(level=2, label="First")
        m.Section.objects.create(program=self.program, year_level=year, name="a")
        program = m.Program.objects.create(code="SECOND", name="Program", department=self.department)
        m.Section.objects.create(program=program, year_level=self.year, name="a")

    def test_edit_and_legitimate_duplicate_names(self):
        self.department.code = " cs "
        self.department.full_clean()
        self.department.save()
        m.Department.objects.create(code="OTHER", name="Computing").full_clean()
        m.Faculty.objects.create(employee_id="EMP002B", full_name="Same Name", department=self.department).full_clean()
        m.Student.objects.create(student_number="001235", full_name="Same Name", section=self.section).full_clean()
        self.student.refresh_from_db()
        self.assertEqual(self.student.student_number, "001234")
        self.assertIsNone(self.student.user_id)

    def test_forms_and_admin_field_errors(self):
        form = MODEL_FORMS["departments"](dict(code=" cs ", name="Other"))
        self.assertFalse(form.is_valid())
        self.assertIn("already exists", form.errors["code"][0])
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser("identity-admin", password="test")
        form_class = admin.site._registry[m.Department].get_form(request)
        form = form_class(dict(code="cS", name="Other"))
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)

    def test_bypassed_updates_and_raw_sql_are_rejected(self):
        other = m.Department.objects.create(code="OTHER", name="Other")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Department.objects.filter(pk=other.pk).update(code="\tcs\n")
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE schedules_department SET code=%s WHERE id=%s", [" Cs ", other.pk])
        other.refresh_from_db()
        self.assertEqual(other.code, "OTHER")

    def test_import_skip_update_and_repeated_normalized_keys(self):
        importer = Importer(self.term, "skip")
        importer.row = 2
        obj = importer.upsert(m.Department, {"code": " cs "}, {"name": "Computing"})
        repeated = importer.upsert(m.Department, {"code": "cS"}, {"name": "Computing"})
        self.assertEqual(obj.pk, repeated.pk)
        self.assertEqual(obj.pk, self.department.pk)
        importer = Importer(self.term, "update")
        importer.row = 2
        importer.upsert(m.Department, {"code": "Cs"}, {"name": "Updated"})
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, "Updated")
        self.assertEqual(self.department.code, "CS")
        self.assertEqual(m.Department.objects.count(), 1)

    def test_workbook_lookup_preserves_existing_record(self):
        obj, created = identity_get_or_create(m.Department, code=" cs ", defaults={"name": "Other"})
        self.assertFalse(created)
        self.assertEqual(obj.pk, self.department.pk)
        self.assertEqual(obj.name, "Computing")

    def workbook_records(self):
        faculty = m.Faculty.objects.create(employee_id=" xls-example ", full_name="Example", department=self.department)
        room = m.Room.objects.create(name=" lab one ", capacity=50, room_type="LECTURE")
        return faculty, room

    def test_full_workbook_persistence_uses_normalized_existing_records(self):
        from .management.commands import import_tertiary_full as module
        faculty, room = self.workbook_records()
        data = dict(program="BSCS", year=1, section="A", faculty="EXAMPLE", duration=60,
                    room="LAB ONE", room_type="LECTURE", units="3", code="NEW101", title="Example",
                    component="LECTURE", source_key="synthetic", sheet="Example", row=2,
                    day=0, start=time(9), end=time(10))
        with patch.dict(module.PROGRAMS, {"BSCS": ("cs", "Computing", "Program")}, clear=True):
            result = module.Command().persist([data])
        entry = result["schedule"].entries.get()
        self.assertEqual(entry.room_id, room.pk)
        self.assertEqual(entry.assignment.faculty_id, faculty.pk)
        self.assertEqual(m.Department.objects.count(), 1)

    def test_sample_workbook_persistence_uses_normalized_existing_records(self):
        from .management.commands import import_tertiary_sample as module
        faculty, room = self.workbook_records()
        row = SimpleNamespace(instructor="EXAMPLE", room="LAB ONE", course_code="NEW101", description="Example", units=3)
        data = dict(row=row, program="BSCS", year=1, section="A", day=0,
                    start=time(9), end=time(10), hours=1, room_type="LECTURE")
        with patch.dict(module.PROGRAMS, {"BSCS": ("cs", "Computing", "Program")}, clear=True):
            module.Command().persist([row], [data])
        self.assertEqual(m.TeachingAssignment.objects.get().faculty_id, faculty.pk)
        self.assertEqual(m.Availability.objects.filter(room=room).count(), 1)
        self.assertEqual(m.Department.objects.count(), 1)
