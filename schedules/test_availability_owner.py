from datetime import time
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from . import models as m
from .forms import AvailabilityForm


class AvailabilityOwnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        dept = m.Department.objects.create(code="OWN", name="Owner tests")
        program = m.Program.objects.create(code="OWN", name="Program", department=dept)
        year = m.YearLevel.objects.create(level=1, label="First")
        cls.faculty = m.Faculty.objects.create(department=dept, employee_id="EMP1", full_name="Synthetic Faculty")
        cls.room = m.Room.objects.create(name="Room A", capacity=50, room_type="LECTURE")
        cls.section = m.Section.objects.create(program=program, year_level=year, name="A")

    def payload(self, **changes):
        data = dict(owner_type="faculty", faculty=self.faculty.pk, day=0, start_time="09:00", end_time="10:00", kind="AVAILABLE")
        data.update(changes)
        return data

    def test_each_owner_saves_alone_and_initializes_edit(self):
        for name in ("faculty", "room", "section"):
            data = self.payload(faculty="", owner_type=name)
            data[name] = getattr(self, name).pk
            form = AvailabilityForm(data)
            self.assertTrue(form.is_valid(), form.errors)
            obj = form.save()
            self.assertEqual(sum(bool(getattr(obj, key + "_id")) for key in form.owners), 1)
            edit = AvailabilityForm(instance=obj)
            self.assertEqual(edit.initial["owner_type"], name)
            self.assertEqual(edit.initial[name], getattr(self, name).pk)

    def test_missing_multiple_and_mismatched_owners(self):
        cases = [
            (self.payload(owner_type="", faculty=""), "Please select a faculty member, room, or section."),
            (self.payload(faculty=""), "Please choose a faculty member."),
            (self.payload(owner_type="room", faculty=""), "Please choose a room."),
            (self.payload(owner_type="section", faculty=""), "Please choose a section."),
            (self.payload(room=self.room.pk), "Choose only one owner"),
            (self.payload(owner_type="room"), "does not match"),
        ]
        for data, message in cases:
            with self.subTest(data=data):
                form = AvailabilityForm(data)
                self.assertFalse(form.is_valid())
                self.assertIn(message, str(form.errors))
                self.assertNotIn("availability_exactly_one_owner", str(form.errors))
        self.assertEqual(m.Availability.objects.count(), 0)

    def test_restored_draft_and_invalid_owner(self):
        form = AvailabilityForm(initial=self.payload(owner_type="room", room=self.room.pk))
        self.assertIsNone(form.initial["faculty"])
        self.assertEqual(form.initial["room"], self.room.pk)
        ambiguous = self.payload(room=self.room.pk)
        ambiguous.pop("owner_type")
        form = AvailabilityForm(initial=ambiguous)
        self.assertEqual(form.initial["owner_type"], "")
        self.assertTrue(all(form.initial[key] is None for key in form.owners))
        form = AvailabilityForm(self.payload(faculty=999999))
        self.assertFalse(form.is_valid())
        self.assertNotIn("availability_exactly_one_owner", str(form.errors))

    def test_faculty_self_service_stays_locked(self):
        form = AvailabilityForm(self.payload(owner_type="room", faculty="", room=self.room.pk), locked_faculty=self.faculty)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.faculty_id, self.faculty.pk)
        self.assertIsNone(obj.room_id)
        self.assertTrue(form.fields["owner_type"].disabled)

    def test_policy_and_model_validation_still_run(self):
        form = AvailabilityForm(self.payload(owner_type="section", faculty="", section=self.section.pk, kind="PREFERRED"))
        self.assertFalse(form.is_valid())
        self.assertIn("Section availability", str(form.errors))
        self.assertFalse(AvailabilityForm(self.payload(end_time="08:00")).is_valid())
        self.assertFalse(AvailabilityForm(self.payload(start_time="bad")).is_valid())
        with self.assertRaises(ValidationError):
            m.Availability(faculty=self.faculty, room=self.room, day=0, start_time=time(9), end_time=time(10)).full_clean()

    def test_admin_draft_restore_and_failed_submission_preserve_other_fields(self):
        admin = get_user_model().objects.create_user(username="owner-admin")
        m.Profile.objects.create(user=admin, role=m.Role.ADMIN)
        self.client.force_login(admin)
        url = reverse("resource_create", args=["availability"])
        m.FormDraft.objects.create(user=admin, resource="availability", payload=self.payload(
            owner_type="room", room=self.room.pk, day=2, kind="UNAVAILABLE"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIsNone(form.initial["faculty"])
        self.assertEqual(form["room"].value(), self.room.pk)
        self.assertEqual(form["day"].value(), 2)
        self.assertContains(response, "Availability type")
        self.assertContains(response, "Without JavaScript")
        response = self.client.post(url, self.payload(faculty="", day=2, kind="UNAVAILABLE"))
        self.assertContains(response, "Please choose a faculty member.")
        self.assertEqual(response.context["form"]["day"].value(), "2")
        self.assertEqual(response.context["form"]["start_time"].value(), "09:00")
        self.assertEqual(response.context["form"]["kind"].value(), "UNAVAILABLE")
        self.assertFalse(m.Availability.objects.exists())
