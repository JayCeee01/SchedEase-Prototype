from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from . import models as m


class FacultyCredentialBatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("batch-admin", password="test")
        department = m.Department.objects.create(code="BATCH", name="Example")
        cls.faculty = m.Faculty.objects.create(employee_id="EMP001A", department=department, full_name="Example Faculty")
        cls.credentials = [m.Credential.objects.create(name=name) for name in ("License A", "License B")]

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("resource_create", args=["faculty-credentials"])
        self.payload = dict(faculty=self.faculty.pk, credential=[c.pk for c in self.credentials],
                            issued_by="Example issuer", issued_on="2026-01-01", expires_on="2027-12-31", notes="Example notes")

    def test_multiple_selection_creates_separate_records_with_metadata(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "apply to every selected credential")
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 302)
        rows = list(m.FacultyCredential.objects.order_by("credential_id"))
        self.assertEqual([r.credential_id for r in rows], [c.pk for c in self.credentials])
        for row in rows:
            self.assertEqual(row.faculty_id, self.faculty.pk)
            self.assertEqual(row.issued_on, date(2026, 1, 1))
            self.assertEqual(row.expires_on, date(2027, 12, 31))
            self.assertEqual(row.issued_by, "Example issuer")
            self.assertEqual(row.notes, "Example notes")

    def test_existing_association_rejects_entire_batch_without_overwrite(self):
        existing = m.FacultyCredential.objects.create(faculty=self.faculty, credential=self.credentials[0], notes="Keep this")
        response = self.client.post(self.url, self.payload)
        self.assertContains(response, "Already assigned: License A")
        self.assertEqual(m.FacultyCredential.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.notes, "Keep this")
        self.assertIsNone(existing.issued_on)

    def test_invalid_and_empty_selection_save_nothing(self):
        for selection in ([], [999999], [self.credentials[0].pk, 999999]):
            response = self.client.post(self.url, {**self.payload, "credential": selection})
            self.assertEqual(response.status_code, 200)
            self.assertIn("credential", response.context["form"].errors)
            self.assertFalse(m.FacultyCredential.objects.exists())

    def test_repeated_selected_id_is_not_created_twice(self):
        response = self.client.post(self.url, {**self.payload, "credential": [self.credentials[0].pk] * 2})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.FacultyCredential.objects.count(), 1)

    def test_failed_second_save_rolls_back_and_retains_draft(self):
        draft = m.FormDraft.objects.create(user=self.admin, resource="faculty-credentials", payload=self.payload)
        save = m.FacultyCredential.save
        calls = []
        def failing_save(instance, *args, **kwargs):
            calls.append(instance.credential_id)
            if len(calls) == 2:
                raise IntegrityError("Simulated competing insert")
            return save(instance, *args, **kwargs)
        with patch.object(m.FacultyCredential, "save", failing_save):
            response = self.client.post(self.url, self.payload)
        self.assertContains(response, "No credentials from this batch were saved.")
        self.assertFalse(m.FacultyCredential.objects.exists())
        self.assertTrue(m.FormDraft.objects.filter(pk=draft.pk).exists())

    def test_edit_updates_only_selected_association(self):
        self.client.post(self.url, self.payload)
        row, other = list(m.FacultyCredential.objects.order_by("pk"))
        before = m.FacultyCredential.objects.values().get(pk=other.pk)
        url = reverse("resource_update", args=["faculty-credentials", row.pk])
        response = self.client.get(url)
        self.assertContains(response, '<select name="credential"')
        response = self.client.post(url, {**self.payload, "credential": row.credential_id, "notes": "Changed"})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.notes, "Changed")
        self.assertEqual(before, m.FacultyCredential.objects.values().get(pk=other.pk))

    def test_draft_restores_all_selected_credentials_and_is_removed_on_success(self):
        response = self.client.post(reverse("save_form_draft"), dict(resource="faculty-credentials", object_pk="", changed=True, payload=self.payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.url)
        self.assertEqual(set(map(str, response.context["form"]["credential"].value())), set(str(c.pk) for c in self.credentials))
        self.client.post(self.url, self.payload)
        self.assertFalse(m.FormDraft.objects.exists())

    def test_non_administrators_cannot_create_associations(self):
        for role in (m.Role.STUDENT, m.Role.FACULTY):
            user = User.objects.create_user("batch-" + role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertIn(self.client.post(self.url, self.payload).status_code, (302, 403))
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        self.assertFalse(m.FacultyCredential.objects.exists())
