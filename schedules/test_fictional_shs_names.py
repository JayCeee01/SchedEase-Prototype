from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase, override_settings

from . import models as m
from .management.commands.seed_fictional_shs_uat import populate
from .management.commands.rename_fictional_shs_uat import protected_state
from .services.fictional_shs_names import apply_names, FACULTY


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FictionalNamingTests(TestCase):
    def test_rename_preserves_every_non_label_field_and_is_idempotent(self):
        get_user_model().objects.create_superuser('existing-admin', password='Unchanged-test-only')
        passwords = {f'fua_faculty_{i+1:02}': 'Strong-isolated-test-password' for i in range(20)}
        passwords.update({f'fua_student_{i+1:02}': 'Strong-isolated-test-password' for i in range(8)})
        with patch('schedules.services.fictional_shs_names.apply_names'):
            populate(passwords)
        before = protected_state()
        with transaction.atomic():
            self.assertEqual(apply_names(), 242)
        self.assertEqual(before, protected_state())
        self.assertEqual(apply_names(), 0)
        self.assertEqual(set(m.Faculty.objects.values_list('full_name', flat=True)), set(FACULTY))
        self.assertEqual(m.Student.objects.values('full_name').distinct().count(), 160)
        self.assertEqual(m.Room.objects.filter(room_type='LECTURE', name__startswith='Lecture Room ').count(), 8)
        self.assertEqual(m.Room.objects.filter(room_type='COMPUTER_LAB', name__startswith='Computer Laboratory ').count(), 4)
        self.assertEqual(m.Section.objects.filter(name='A').count(), 8)
        self.assertEqual(m.Subject.objects.count(), 32)
        self.assertFalse(m.Subject.objects.filter(title__startswith='Fictional').exists())
        self.assertEqual(get_user_model().objects.count(), 29)
        self.assertEqual(m.Assignment.objects.count(), 64)
        self.assertFalse(m.Schedule.objects.exists())
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA integrity_check')
            self.assertEqual(cursor.fetchall(), [('ok',)])
            cursor.execute('PRAGMA foreign_key_check')
            self.assertEqual(cursor.fetchall(), [])
