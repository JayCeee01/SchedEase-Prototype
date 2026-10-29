from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase, override_settings

from . import models as m
from .management.commands.seed_fictional_shs_uat import populate, verify_dataset


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FictionalSHSUATTests(TestCase):
    def test_population_idempotency_links_and_admin_preservation(self):
        admin = get_user_model().objects.create_superuser('existing-admin', password='unchanged-test-only')
        before = get_user_model().objects.get(pk=admin.pk).__dict__.copy()
        passwords = {f'fua_faculty_{i+1:02}': 'Isolated-test-only-long-password' for i in range(20)}
        passwords.update({f'fua_student_{i+1:02}': 'Isolated-test-only-long-password' for i in range(8)})
        with transaction.atomic():
            self.assertTrue(populate(passwords))
        self.assertFalse(populate(passwords))
        self.assertEqual(verify_dataset()['Assignment'], 64)
        self.assertEqual(m.Student.objects.filter(user__isnull=False).count(), 8)
        self.assertEqual(m.Faculty.objects.filter(user__isnull=False).count(), 20)
        self.assertEqual(get_user_model().objects.get(pk=admin.pk).password, before['password'])
        self.assertFalse(m.Schedule.objects.exists())

    def test_conflicting_records_rejected_without_changes(self):
        m.Department.objects.create(code='OTHER', name='Existing')
        with self.assertRaises(CommandError), transaction.atomic():
            populate({})
        self.assertEqual(m.Department.objects.count(), 1)
        self.assertFalse(m.CurriculumVersion.objects.exists())
