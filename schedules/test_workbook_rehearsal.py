from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import TestCase
from . import models as m
from .management.commands.rehearse_workbook_uat import Command, populate


class WorkbookRehearsalSafetyTests(TestCase):
    def test_repository_target_rejected_before_database_access(self):
        path = Path(settings.BASE_DIR) / 'README.md'
        with patch.dict(connection.settings_dict, NAME=str(path)):
            with self.assertRaisesMessage(CommandError, 'external disposable'):
                Command().handle(workbook='unused', level='SHS', expected_sha256='unused')

    def test_incomplete_workbook_rolls_back_clear_and_preserves_account(self):
        user = get_user_model().objects.create_user('preserved-account')
        department = m.Department.objects.create(code='KEEP', name='Preserved by rollback')
        book = Workbook()
        book.active.title = '02 Programs'
        book.active.append(['Code'])
        with patch('schedules.management.commands.rehearse_workbook_uat.openpyxl.load_workbook', return_value=book):
            with self.assertRaises(KeyError), transaction.atomic():
                populate('synthetic.xlsx', 'SHS')
        self.assertTrue(m.Department.objects.filter(pk=department.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())
