from .test_publication_helpers import finalize as finalize_fixture, legacy_case, upgrade
"""Finalized SHS dependency enforcement using disposable fixtures."""
from copy import deepcopy
from importlib import import_module
import json
import subprocess
import sys
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, SimpleTestCase
from . import models as m
from . import test_shs_generation as generation
from . import test_contact_workload as workload
from .protection import protected, archive_transition
from .services.participation_dependencies import affected_schedules


def fixture(owner, finalize=True):
    generation.ControlledSHSGenerationTests.setUp(owner)
    owner.config.is_confirmed = False
    owner.config.combined_class_reference = 'Synthetic combined approval'
    owner.config.save()
    owner.extra_department = m.Department.objects.create(code='EXTRA', name='Extra')
    owner.extra_program = m.Program.objects.create(department=owner.extra_department,
        code='EXTRA', name='Extra SHS', education_level='SHS')
    owner.extra = m.Section.objects.create(program=owner.extra_program,
        year_level=owner.year, cohort=owner.section.cohort, name='B', size=20)
    owner.participation = m.SHSSectionParticipation.objects.create(configuration=owner.config, section=owner.extra)
    owner.config.is_confirmed = True
    owner.config.save()
    workload.ContactPolicyTests.policy(owner)
    owner.schedule = generation.ControlledSHSGenerationTests.generate(owner)
    if finalize:
        finalize_fixture(owner.schedule)


class ParticipationProtectionTests(TestCase):
    def setUp(self):
        fixture(self)

    def test_primary_additional_and_parents_both_layers(self):
        records = [(self.section, 'size', 21), (self.extra, 'size', 21),
                   (self.extra_program, 'name', 'Changed'), (self.year, 'label', 'Changed'),
                   (self.extra_department, 'name', 'Changed')]
        before = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data
        for obj, field, value in records:
            with self.subTest(model=obj._meta.model_name, pk=obj.pk):
                self.assertTrue(protected(obj))
                self.assertIn((self.schedule.pk, 0), affected_schedules(obj._meta.model_name, obj.pk))
                setattr(obj, field, value)
                with self.assertRaises(ValidationError): obj.save()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(**{field: value})
                with self.assertRaises(ProtectedError), transaction.atomic(): obj.delete()
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM {obj._meta.db_table} WHERE id=%s', [obj.pk])
                obj.refresh_from_db()
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, before)

    def test_archived_dependencies_retained(self):
        finalize_fixture(self.schedule, archived=True)
        self.assertTrue(protected(self.extra))
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.filter(pk=self.extra.pk).update(size=99)

    def test_participation_insertion_deletion_and_replacement(self):
        extra = m.Section.objects.create(program=self.program, year_level=self.year,
                                        cohort=self.section.cohort, name='C', size=1)
        with self.assertRaises(ValidationError):
            m.SHSSectionParticipation.objects.create(configuration=self.config, section=extra)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SHSSectionParticipation.objects.bulk_create([
                m.SHSSectionParticipation(configuration=self.config, section=extra)])
        with self.assertRaises(ProtectedError), transaction.atomic(): self.participation.delete()
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('DELETE FROM schedules_shssectionparticipation WHERE id=%s', [self.participation.pk])
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT OR REPLACE INTO schedules_shssectionparticipation (id,configuration_id,section_id) VALUES (%s,%s,%s)',
                           [self.participation.pk, self.config.pk, extra.pk])

    @legacy_case
    def test_reassignment_checks_old_and_new_configuration(self):
        parent = m.Assignment.objects.create(term=self.term, subject=self.subject,
                                            faculty=self.faculty, section=self.extra)
        other = m.SHSAssignmentConfiguration.objects.create(assignment=parent, delivery_plan=self.plan,
            combined_class_reference='Synthetic approval')
        free = m.SHSSectionParticipation.objects.create(configuration=other, section=self.section)
        upgrade()
        for row, config, section in ((self.participation, other, self.section),
                                     (free, self.config, self.extra)):
            with self.subTest(old=row.configuration_id, new=config.pk):
                row.configuration, row.section = config, section
                with self.assertRaises(ValidationError): row.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.SHSSectionParticipation.objects.filter(pk=row.pk).update(configuration=config, section=section)
                row.refresh_from_db()
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT OR REPLACE INTO schedules_shssectionparticipation (id,configuration_id,section_id) VALUES (%s,%s,%s)',
                           [self.participation.pk, other.pk, self.section.pk])

    def test_bulk_update_and_parent_replacement(self):
        free = m.Section.objects.create(program=self.program, year_level=self.year,
                                       cohort=self.section.cohort, name='FREE', size=10)
        free.size = self.extra.size = 25
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.bulk_update([free, self.extra], ['size'], batch_size=1)
        free.refresh_from_db()
        self.assertEqual(free.size, 10)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT OR REPLACE INTO schedules_department (id,code,name) VALUES (%s,%s,%s)',
                           [self.extra_department.pk, 'EXTRA', 'Changed'])

    def test_unrelated_records_and_noop_remain_editable(self):
        self.extra.save()
        m.Section.objects.filter(pk=self.extra.pk).update(size=self.extra.size)
        free = m.Department.objects.create(code='FREE', name='Free')
        self.assertFalse(protected(free))
        free.name = 'Renamed'
        free.save()
        self.assertEqual(affected_schedules('department', free.pk), ())

    def test_replacement_by_unique_key_with_different_id_is_blocked(self):
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT OR REPLACE INTO schedules_department (id,code,name) VALUES (%s,%s,%s)',
                           [99999, ' extra ', 'Replacement'])
        free = m.Department.objects.create(code='FREE', name='Free')
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE OR REPLACE schedules_department SET code=%s WHERE id=%s', ['EXTRA', free.pk])
        self.assertTrue(m.Department.objects.filter(pk=self.extra_department.pk).exists())

    def test_missing_installed_dependency_view_is_not_safe(self):
        # Deliberately damage only disposable storage; the enclosing TestCase
        # transaction restores the view after this fault-injection test.
        with connection.cursor() as cursor:
            cursor.execute('DROP VIEW shs_finalized_participation_v1')
        with self.assertRaisesMessage(ValidationError, 'protection is unavailable'):
            protected(self.extra)


class LegacyEvidenceTests(TestCase):
    def setUp(self): fixture(self, finalize=False)

    def finalize(self):
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()
        upgrade()

    @legacy_case
    def test_frozen_only_section_and_parents_remain_dependencies(self):
        self.participation.delete()
        self.finalize()
        for obj in (self.extra, self.extra_program, self.extra_department):
            self.assertTrue(protected(obj))
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.filter(pk=self.extra.pk).update(size=99)

    def test_draft_participation_can_change(self):
        self.assertFalse(protected(self.extra))
        self.extra.size = 19
        self.extra.save()
        self.participation.delete()
        self.assertFalse(m.SHSSectionParticipation.objects.exists())

    @legacy_case
    def test_missing_binding_blocks_uncertain_references(self):
        self.schedule.entries.get().assignment.shs_binding.delete()
        self.finalize()
        free = m.Department.objects.create(code='FREE', name='Free')
        self.assertIn((self.schedule.pk, 1), affected_schedules('department', free.pk))
        with self.assertRaises(ValidationError):
            free.name = 'Changed'
            free.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Department.objects.filter(pk=free.pk).update(name='Changed')

    @legacy_case
    def test_live_only_participation_is_also_a_dependency(self):
        extra = m.Section.objects.create(program=self.extra_program, year_level=self.year,
                                        cohort=self.section.cohort, name='C', size=1)
        m.SHSSectionParticipation.objects.create(configuration=self.config, section=extra)
        self.finalize()
        self.assertIn((self.schedule.pk, 0), affected_schedules('section', extra.pk))
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.filter(pk=extra.pk).update(size=2)

    @legacy_case
    def test_missing_or_malformed_finalized_history_fails_closed(self):
        self.finalize()
        snapshot = m.ScheduleSnapshot.objects.get(schedule=self.schedule)
        original = deepcopy(snapshot.data)
        duplicate = deepcopy(original)
        duplicate['entries'].append(deepcopy(duplicate['entries'][0]))
        guards = import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS
        for data in (None, [], {}, duplicate):
            with self.subTest(data=data), transaction.atomic():
                # Fault injection exclusively in the disposable test database.
                # Restore the original trigger before exercising any guards.
                with connection.cursor() as cursor:
                    cursor.execute('DROP TRIGGER h2_snapshot_update')
                    try:
                        cursor.execute('UPDATE schedules_schedulesnapshot SET data=%s WHERE id=%s',
                                       [json.dumps(data), snapshot.pk])
                    finally:
                        cursor.execute(guards['h2_snapshot_update'])
                self.assertIn((self.schedule.pk, 1), affected_schedules('section', self.extra.pk))
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.Section.objects.filter(pk=self.extra.pk).update(size=21)
                transaction.set_rollback(True)
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER h2_snapshot_delete')
            try:
                cursor.execute('DELETE FROM schedules_schedulesnapshot WHERE id=%s', [snapshot.pk])
            finally:
                cursor.execute(guards['h2_snapshot_delete'])
        self.assertIn((self.schedule.pk, 1), affected_schedules('section', self.extra.pk))
        self.assertTrue(protected(self.extra))

    @legacy_case
    def test_malformed_and_inconsistent_bindings_fail_closed(self):
        binding = self.schedule.entries.get().assignment.shs_binding
        original = deepcopy(binding.data)
        variants = ['null', [], 'invalid', {}, {**original, 'sections': []},
                    {**original, 'sections': [False]},
                    {**original, 'sections': [{'id': str(self.extra.pk)}]},
                    {**original, 'configuration_id': 999999},
                    {**original, 'sections': [original['sections'][0]] * 2},
                    {**original, 'sections': list(reversed(original['sections']))}]
        for data in variants:
            with self.subTest(data=data), transaction.atomic():
                binding.delete()
                m.SHSMeetingBinding.objects.bulk_create([m.SHSMeetingBinding(
                    meeting_id=binding.meeting_id, pattern_id=binding.pattern_id, data=data)])
                self.finalize()
                free = m.Department.objects.create(code='FREE', name='Free')
                self.assertTrue(protected(free))
                self.assertIn((self.schedule.pk, 1), affected_schedules('department', free.pk))
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.Department.objects.filter(pk=free.pk).update(name='Changed')
                transaction.set_rollback(True)
            binding = self.schedule.entries.get().assignment.shs_binding
            self.schedule.refresh_from_db()


class ParticipationMigrationTests(SimpleTestCase):
    def test_populated_forward_reverse_preserves_data_and_old_triggers(self):
        script = r'''
import os
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection, IntegrityError
from types import SimpleNamespace
from schedules.test_participation_protection import fixture
from schedules import models as m
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0027',verbosity=0)
f=SimpleNamespace()
fixture(f)
def inventory():
    with connection.cursor() as c:
        c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
        triggers=dict(c.fetchall())
        data={}
        for table in connection.introspection.table_names():
            if table!='django_migrations':
                c.execute('SELECT * FROM '+connection.ops.quote_name(table)+' ORDER BY 1')
                data[table]=c.fetchall()
        return triggers,data
before,records=inventory()
call_command('migrate','schedules','0028',verbosity=0)
after,current=inventory()
assert records==current
assert all(after[k]==v for k,v in before.items())
try:
    m.Section.objects.filter(pk=f.extra.pk).update(size=99)
except IntegrityError:
    pass
else:
    raise AssertionError('Additional section was not protected')
with connection.cursor() as c:
    c.execute('PRAGMA integrity_check')
    assert c.fetchall()==[('ok',)]
    c.execute('PRAGMA foreign_key_check')
    assert c.fetchall()==[]
call_command('migrate','schedules','0027',verbosity=0)
assert inventory()==(before,records)
call_command('migrate','schedules','0028',verbosity=0)
assert inventory()==(after,records)
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True,
                                text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
