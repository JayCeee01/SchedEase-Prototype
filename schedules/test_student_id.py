"""Strict new IDs and narrowly scoped legacy edit compatibility."""
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from . import models as m
from .forms import StudentForm, MODEL_FORMS


class StudentIDTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = m.Department.objects.create(code="ID", name="Identifiers")
        program = m.Program.objects.create(code="ID", name="Program", department=cls.department)
        year = m.YearLevel.objects.create(level=1, label="First")
        cls.section = m.Section.objects.create(program=program, year_level=year, name="A")
        cls.administrator = User.objects.create_superuser(username="id-admin", password="test-only-password")

    def data(self, number, **changes):
        return dict(section=self.section.pk, student_number=number, full_name="Synthetic Student", **changes)

    def test_valid_ids_preserve_text_and_optional_account(self):
        for value in ("123456", "001234"):
            form = StudentForm(self.data(value))
            self.assertTrue(form.is_valid(), form.errors)
            obj = form.save()
            obj.refresh_from_db()
            self.assertEqual(obj.student_number, value)
            self.assertIsNone(obj.user_id)
            obj.full_clean()

    def test_invalid_new_ids_rejected_by_form_and_model(self):
        for value in ("STU001", "123-456", "123 456", " 123", "123 ", "123\n", "", "???", "???", "123\t"):
            with self.subTest(value=value):
                form = StudentForm(self.data(value))
                self.assertFalse(form.is_valid())
                self.assertIn("student_number", form.errors)
                with self.assertRaises(ValidationError):
                    m.Student(section=self.section, full_name="Test", student_number=value).full_clean()

    def test_legacy_unchanged_edit_and_strict_model(self):
        # Raw ORM fixture represents pre-validator data; save() does not call full_clean().
        obj = m.Student.objects.create(section=self.section, full_name="Old", student_number=" LEGACY-1 ")
        form = StudentForm(self.data(obj.student_number), instance=obj)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        obj.refresh_from_db()
        self.assertEqual(obj.student_number, " LEGACY-1 ")
        self.assertEqual(obj.full_name, "Synthetic Student")
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_changed_legacy_id_requires_digits(self):
        obj = m.Student.objects.create(section=self.section, full_name="Old", student_number="OLD")
        for value in ("NEW", " OLD "):
            obj.refresh_from_db()
            form = StudentForm(self.data(value), instance=obj)
            self.assertFalse(form.is_valid())
        obj.refresh_from_db()
        form = StudentForm(self.data("0007"), instance=obj)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(m.Student.objects.get(pk=obj.pk).student_number, "0007")

    def test_forged_initial_or_instance_does_not_bypass_new_validation(self):
        obj = m.Student.objects.create(section=self.section, full_name="Old", student_number="OLD")
        obj.student_number = "FORGED"
        self.assertFalse(StudentForm(self.data("FORGED"), instance=obj, initial={"student_number": "FORGED"}).is_valid())
        new = m.Student(pk=obj.pk, section=self.section, student_number="OLD")
        self.assertFalse(StudentForm(self.data("OLD"), instance=new).is_valid())

    def test_uniqueness_and_account_link_preserved(self):
        user = User.objects.create_user(username="linked-student")
        first = StudentForm(self.data("001", user=user.pk))
        self.assertTrue(first.is_valid(), first.errors)
        obj = first.save()
        self.assertEqual(obj.user_id, user.pk)
        self.assertFalse(StudentForm(self.data("001")).is_valid())
        self.assertFalse(StudentForm(self.data("002", user=user.pk)).is_valid())
        edit = StudentForm(self.data("001", user=user.pk), instance=obj)
        self.assertTrue(edit.is_valid(), edit.errors)

    def test_employee_ids_unchanged_and_hints_render(self):
        form = MODEL_FORMS["faculty"](dict(department=self.department.pk, employee_id="EMP001A", full_name="Faculty", max_weekly_hours=24))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().employee_id, "EMP001A")
        html = StudentForm().as_p()
        self.assertIn('inputmode="numeric"', html)
        self.assertIn("Student ID", html)

    def test_application_and_admin_paths_use_same_rules(self):
        self.client.force_login(self.administrator)
        # Exercise actual registered admin form without changing permission classes.
        request = RequestFactory().get("/admin/")
        request.user = self.administrator
        form_class = admin.site._registry[m.Student].get_form(request)
        self.assertFalse(form_class(self.data("BAD")).is_valid())
        obj = m.Student.objects.create(section=self.section, full_name="Old", student_number="OLD")
        edit_class = admin.site._registry[m.Student].get_form(request, obj)
        form = edit_class(self.data("OLD"), instance=obj)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(MODEL_FORMS["students"], StudentForm)

    def test_http_student_edits_and_access(self):
        self.client.force_login(self.administrator)
        response = self.client.post("/schedules/manage/students/new/", self.data("BAD"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student ID must contain numbers only")
        self.assertFalse(m.Student.objects.exists())
        response = self.client.post("/schedules/manage/students/new/", self.data("00042"))
        self.assertEqual(response.status_code, 302)
        obj = m.Student.objects.get()
        # Introduce a legacy fixture only in the disposable test database.
        m.Student.objects.filter(pk=obj.pk).update(student_number="OLD")
        url = f"/schedules/manage/students/{obj.pk}/edit/"
        response = self.client.post(url, self.data("OLD"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.Student.objects.get(pk=obj.pk).student_number, "OLD")
        response = self.client.post(url, self.data("OTHER"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(m.Student.objects.get(pk=obj.pk).student_number, "OLD")
        ordinary = User.objects.create_user(username="not-admin")
        self.client.force_login(ordinary)
        response = self.client.post(url, self.data("999"))
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(m.Student.objects.get(pk=obj.pk).student_number, "OLD")
